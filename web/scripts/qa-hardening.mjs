// SPEC-HARDENING, run from qa.mjs (online; `--hardening-only` runs just these). No job starts anywhere.
// Server side, on the real route code: a second `next start` (this build) on :3106 pointed at a recording stand-in engine
// on :8799 (never the real one), started three times: no passcode with a token, no passcode without a token, and a
// passcode. §1: without a passcode the session JSON carries no token (and says `direct` only when the engine needs none);
// with one, the token after unlocking. §2: a segment holding an encoded "/" (%2F, %252F), "\" (%5C) or a leading "." is
// refused (400) before the engine; ".." and %2e%2e are resolved by Next before the route runs, so no dot segment ever
// reaches the engine and, locked, none steps around the owner check; a plain encoded name still passes as it was; a
// redirecting engine answer is a 502 whose target is never asked. §3: /api/report/… through the relay is 401 locked (nothing
// reaches the engine) and 200 unlocked (with the relay's token).
// Browser, on the site under test: its own session JSON holds no token without a passcode; Download report on the Edit
// workspace (1019-113515-… v4, the session answered as locked here) says "Needs the passcode", a click opens the Unlock
// dialog and asks nothing of /api/report; after the passcode (answered here) the waiting click downloads the report
// through the relay. /api/report is answered in the browser.
import { spawn } from "node:child_process";
import { createServer, get } from "node:http";

const EDIT_CID = "1019-113515-use-same-game-design-same";
const TOKEN = "qa-relay-token";
const PASSCODE = "qa-passcode";
const NEXT = "http://localhost:3106";
const R = `${NEXT}/api/engine/relay`;

export default async function hardeningChecks({ base, check, featurePage }) {
  await browserChecks({ base, check, featurePage });
  if (/localhost|127\.0\.0\.1/.test(base)) await serverChecks(check);
}

/** a GET sent exactly as written (fetch and URL would resolve "..") */
const raw = (path, headers = {}) =>
  new Promise((ok, fail) => {
    get({ host: "127.0.0.1", port: 3106, path, headers }, (r) => {
      let body = "";
      r.on("data", (c) => (body += c));
      r.on("end", () => ok({ status: r.statusCode, body }));
    }).on("error", fail);
  });

async function withNext(env, run) {
  const next = spawn("node_modules/.bin/next", ["start", "-p", "3106"], {
    env: { ...process.env, ENGINE_URL: "http://127.0.0.1:8799", PORT: "3106", ...env },
    stdio: "ignore",
  });
  try {
    for (let i = 0; i < 60; i++) {
      if (await fetch(`${NEXT}/api/session`).then((r) => r.ok, () => false)) break;
      await new Promise((ok) => setTimeout(ok, 500));
    }
    await run();
  } finally {
    next.kill("SIGTERM");
    await new Promise((ok) => next.once("exit", ok));
  }
}

async function serverChecks(check) {
  const seen = [];
  const stolen = [];
  const engine = createServer((req, res) => {
    seen.push({ method: req.method, path: req.url, auth: req.headers.authorization });
    req.resume();
    if (req.url.startsWith("/studio/redirect/")) {
      res.writeHead(302, { Location: "http://127.0.0.1:8797/stolen" });
      return res.end();
    }
    if (req.url.startsWith("/api/report/")) {
      res.setHeader("Content-Type", "text/markdown");
      return res.end("# qa report\n");
    }
    res.setHeader("Content-Type", "application/json");
    res.end("{}");
  });
  const elsewhere = createServer((req, res) => {
    stolen.push({ path: req.url, auth: req.headers.authorization });
    res.end("{}");
  });
  await new Promise((ok) => engine.listen(8799, "127.0.0.1", ok));
  await new Promise((ok) => elsewhere.listen(8797, "127.0.0.1", ok));
  const quiet = async (what, fn) => {
    const n = seen.length;
    const r = await fn();
    return { ...r, reached: seen.slice(n), what };
  };
  try {
    // ── no passcode, a token-protected engine ────────────────────────────────────────────────────
    await withNext({ ENGINE_TOKEN: TOKEN, STUDIO_PASSCODE: "" }, async () => {
      const text = await fetch(`${NEXT}/api/session`).then((r) => r.text());
      const s = JSON.parse(text);
      check(s.unlocked === true && s.required === false && s.engine && !("token" in s.engine) && !text.includes(TOKEN), `hardening §1: no passcode → the session JSON carries no engine.token (${text})`);
      check(s.engine?.direct === false, "hardening §1: no passcode, a token-protected engine → direct: false (the browser uses the relay)");

      // §2: refused before the engine
      for (const [path, want] of [
        ["/api/engine/relay/studio/a%2Fb/v1/brief.json", [400]],
        ["/api/engine/relay/studio/a%2fb/v1/brief.json", [400]],
        ["/api/engine/relay/studio/a%252Fb/v1/brief.json", [400]],
        ["/api/engine/relay/api/creatives%2F..%2Ffeedback", [400]],
        ["/api/engine/relay/studio/a%5Cb/v1/brief.json", [400]],
        ["/api/engine/relay/studio/.hidden/v1/brief.json", [400]],
        ["/api/engine/relay/api/x/../../feedback", [404]],
        ["/api/engine/relay/../session", [404]],
      ]) {
        const r = await quiet(path, () => raw(path));
        check(want.includes(r.status) && r.reached.length === 0, `hardening §2: ${path} refused (${r.status}), nothing reached the engine${r.reached.length ? " GOT " + r.reached.map((x) => x.path).join(",") : ""}`);
      }
      // dot segments that stay inside the relay are resolved by Next before the route runs: the checks see, and the
      // engine gets, the resolved path, never a dot segment (the owner check on them: the passcode block below)
      for (const path of ["/api/engine/relay/studio/../api/meta", "/api/engine/relay/studio/%2e%2e/api/meta", "/api/engine/relay/studio/.%2e/api/meta", "/api/engine/relay/api/./meta"]) {
        const r = await quiet(path, () => raw(path));
        check(r.reached.every((x) => x.path === "/api/meta") && r.reached.every((x) => !/\/(\.|%2e)/i.test(x.path)), `hardening §2: ${path} → ${r.status}, no dot segment reached the engine (${r.reached.map((x) => x.path).join(",") || "nothing"})`);
      }
      // a plain encoded name still goes through, as it was
      {
        const r = await quiet("space", () => raw("/api/engine/relay/studio/a%20b/v1/brief.json"));
        check(r.status === 200 && r.reached.length === 1 && r.reached[0].path === "/studio/a%20b/v1/brief.json", `hardening §2: a plain encoded segment passes unchanged (${r.reached[0]?.path})`);
      }
      // a redirecting engine answer is not followed
      {
        const r = await quiet("redirect", () => raw("/api/engine/relay/studio/redirect/v1/brief.json"));
        check(r.status === 502 && r.reached.length === 1 && stolen.length === 0, `hardening §2: an engine redirect → 502, its target never asked (${r.status}, ${stolen.length} at the target)`);
      }
      // §3 without a passcode the studio is open: the report is relayed with the relay's token
      {
        const r = await quiet("report", () => raw(`/api/engine/relay/api/report/${EDIT_CID}?version=4&format=md`));
        check(r.status === 200 && r.reached[0]?.auth === `Bearer ${TOKEN}`, "hardening §3: no passcode → /api/report through the relay is 200 (the relay adds its token)");
      }
    });

    // ── no passcode, an engine without a token: direct is allowed ───────────────────────────────
    await withNext({ ENGINE_TOKEN: "", STUDIO_PASSCODE: "" }, async () => {
      const s = await fetch(`${NEXT}/api/session`).then((r) => r.json());
      check(s.engine?.direct === true && !("token" in s.engine), "hardening §1: no passcode, no engine token → direct: true, no token key");
    });

    // ── a passcode: the token after unlocking; reports are owner reads ──────────────────────────
    await withNext({ ENGINE_TOKEN: TOKEN, STUDIO_PASSCODE: PASSCODE }, async () => {
      const locked = await fetch(`${NEXT}/api/session`).then((r) => r.text());
      check(!locked.includes(TOKEN) && JSON.parse(locked).unlocked === false, "hardening §1: a passcode, locked → no token");
      const reportPath = `/api/engine/relay/api/report/${EDIT_CID}?version=4&format=md`;
      const before = await quiet("locked report", () => raw(reportPath));
      check(before.status === 401 && before.reached.length === 0, `hardening §3: locked → /api/report through the relay is 401, nothing reached the engine (${before.status})`);
      const login = await fetch(`${NEXT}/api/session`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ passcode: PASSCODE }) });
      const cookie = (login.headers.get("set-cookie") || "").split(";")[0];
      check(login.status === 200 && cookie.startsWith("cbj_studio="), "hardening: the passcode unlocks (a session cookie)");
      const s = await fetch(`${NEXT}/api/session`, { headers: { Cookie: cookie } }).then((r) => r.json());
      check(s.unlocked === true && s.engine?.token === TOKEN && s.engine?.direct === true, "hardening §1: a passcode, unlocked → the token as before (uploads go directly)");
      const after = await quiet("unlocked report", () => raw(reportPath, { Cookie: cookie }));
      check(after.status === 200 && after.body === "# qa report\n" && after.reached[0]?.auth === `Bearer ${TOKEN}`, `hardening §3: unlocked → /api/report through the relay is 200 (${after.status})`);
      const fb = await quiet("feedback", () => raw("/api/engine/relay/api/feedback"));
      check(fb.status === 401 && fb.reached.length === 0, "hardening §3: the other owner reads stay behind the passcode (api/feedback 401)");
      // locked, a dot or encoded path cannot step around the owner check
      for (const path of [
        `/api/engine/relay/studio/../api/report/${EDIT_CID}`,
        `/api/engine/relay/studio/%2e%2e/api/report/${EDIT_CID}`,
        "/api/engine/relay/studio/x/..%2F..%2Fapi/feedback",
        "/api/engine/relay/api/meta%2F..%2Ffeedback",
        "/api/engine/relay/api/meta%252F..%252Ffeedback",
      ]) {
        const r = await quiet(path, () => raw(path));
        check([400, 401, 404].includes(r.status) && r.reached.length === 0, `hardening §2/§3: locked, ${path} refused (${r.status}), nothing reached the engine`);
      }
      const bad = await quiet("bad unlocked", () => raw("/api/engine/relay/api/report%2F..%2Fx", { Cookie: cookie }));
      check(bad.status === 400 && bad.reached.length === 0, "hardening §2: unlocked, an encoded separator is still refused");
    });
  } finally {
    engine.close();
    elsewhere.close();
  }
}

async function browserChecks({ base, check, featurePage }) {
  const own = await fetch(`${base}/api/session`).then((r) => r.json());
  if (!own.required) check(!own.engine || !("token" in own.engine), `hardening §1 (${base}): no passcode → its session JSON has no token`);

  const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
  let unlocked = false;
  const reports = [];
  // locked until the passcode below; then unlocked with no token and no direct path (every call through the relay)
  await page.route("**/api/session", (r) => {
    if (r.request().method() === "POST") {
      unlocked = true;
      return r.fulfill({ json: { unlocked: true, required: true } });
    }
    return r.fulfill({ json: unlocked ? { unlocked: true, required: true, engine: { url: own.engine?.url || "", direct: false } } : { unlocked: false, required: true } });
  });
  await page.route("**/api/report/**", (r) => {
    reports.push(new URL(r.request().url()).pathname);
    return r.fulfill({ status: 200, contentType: "text/markdown", body: "# qa report\n" });
  });
  await page.goto(`${base}/edit?c=${EDIT_CID}&v=4`, { waitUntil: "load" });
  await page.getByText("What changed").first().waitFor({ timeout: 15000 });
  const card = page.getByRole("region", { name: "What changed" });
  const group = card.getByRole("group", { name: "Download report" });
  await group.waitFor({ timeout: 15000 });
  const wrap = group.locator("xpath=..");
  check((await wrap.getByText("Needs the passcode", { exact: true }).count()) === 1, 'hardening §3 browser: locked, Download report says "Needs the passcode"');
  await page.screenshot({ path: "qa/hardening-report-locked-1440.png", scale: "css" });
  await card.getByRole("button", { name: "Download report as Markdown" }).click();
  const unlock = page.getByRole("dialog", { name: "Unlock the studio" });
  await unlock.waitFor({ timeout: 5000 }).catch(() => null);
  check((await unlock.isVisible()) && reports.length === 0, "hardening §3 browser: a locked click opens the Unlock dialog and asks nothing of /api/report");
  await unlock.locator('input[type="password"]').fill("qa");
  const download = page.waitForEvent("download", { timeout: 10000 }).catch(() => null);
  await unlock.getByRole("button", { name: "Unlock", exact: true }).click();
  const file = await download;
  check(
    file?.suggestedFilename() === `${EDIT_CID}-v4-report.md` && reports.length === 1 && reports[0] === `/api/engine/relay/api/report/${EDIT_CID}`,
    `hardening §3 browser: after the passcode the waiting click downloads the report through the relay (${reports.join(",")})`,
  );
  check((await wrap.getByText("Needs the passcode", { exact: true }).count()) === 0, 'hardening §3 browser: unlocked, no "Needs the passcode"');
  check(errors.length === 0, `hardening browser: no page/console errors ${errors.join("; ")}`);
  await ctx.close();
}
