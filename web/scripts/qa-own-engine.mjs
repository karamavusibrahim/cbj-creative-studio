// SPEC-OWN-ENGINE §4, run from qa.mjs (it passes the browser and its check()); `--own-engine-only` runs just these.
// A fake "own engine" at http://127.0.0.1:8765 answered entirely by Playwright routing: no request to that address ever
// leaves the browser (whatever listens there is never contacted). It answers /api/health, /api/meta (the studio
// engine's real meta, read once, as a claude-cli/opus engine with a token), /api/jobs (empty), one plan job, one
// /api/enhance and one /api/feedback POST; its other reads (creatives, studio files, sprites, the owner's records) are
// served from the studio engine of .env.local by GET only, so pages and media render. Every other POST is aborted.
// The studio's session is answered as locked with a passcode, so the gate and the relay are visible. The CORS failure
// needs the browser's real CORS check (a routed answer may get through without the header), so it is asked of a tiny
// local server on a free port that answers without CORS headers.
// Checks, at 1440 and 390: the dialog's two modes (mode B: only the Gemini key, no Anthropic key, planner or model id,
// SPEC-OWN-ENGINE-2), Save disabled before Check, the three failures (not reachable, CORS,
// a wrong token), the Reachable line, Save, the status pill and the header pill, Create's planner line, POSTs on the own
// URL with the token and nothing through the relay (no key headers either), no passcode asked, media on the own host,
// the owner's page without the passcode, the engine going offline mid-session (the setting kept), Clear back to the
// studio's engine and its passcode; at 1440 also the switch back by saving the studio mode. No horizontal overflow,
// no unexpected page or console errors; screenshots qa/own-engine-*.
import { serveCatalogue } from "./qa-catalogue.mjs";
import { engineAuth, engineJson, ENGINE } from "./qa-engine.mjs";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";

const OWN = "http://127.0.0.1:8765";
const TOKEN = "qa-own-token";
const H = ["x-cbj-gemini-key", "x-cbj-anthropic-key", "x-cbj-planner"];
const fixture = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8"));

export default async function ownEngineChecks({ browser, base, check, VIEWPORTS, CID }) {
  const origin = new URL(base).origin;
  const realMeta = await engineJson("/api/meta");
  const meta = { ...realMeta, backend: "claude", models: ["claude-cli/opus"], effort: "low", busy: false, features: { ...realMeta.features, soundtrack: { bed: true, voice: true } } };
  const versions = await engineJson(`/api/creatives/${CID}`);
  const brief = versions.find((x) => x.n === 1).brief;
  const enhance = fixture("enhance-changed");
  const plain = createServer((req, res) => {
    req.resume();
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ ok: true, busy: false, backend: "claude", models: ["claude-cli/opus"] })); // no Access-Control-Allow-Origin
  });
  await new Promise((ok) => plain.listen(0, "127.0.0.1", ok));
  const NOCORS = `http://127.0.0.1:${plain.address().port}`;
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const shot = async (page, name, full = true) => {
    await page.waitForTimeout(400);
    await page.screenshot({ path: `qa/own-engine-${name}.png`, fullPage: full, scale: "css" });
  };

  for (const [vpName, vp] of VIEWPORTS) {
    const tag = `${vpName} own engine:`;
    const ctx = await browser.newContext({ viewport: vp });
    await serveCatalogue(ctx); // a catalogue build asks the bucket on Create and Edit (the sample assets' index)
    const page = await ctx.newPage();
    const errors = [];
    const state = { mode: "ok", tolerate: false }; // ok | down
    const log = { own: [], relay: [], studioHealth: [], aborted: [] };
    const allowed = (t) => state.tolerate && /ERR_|CORS|Failed to load resource|Failed to fetch|status of 401/.test(t);
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      const t = m.text();
      if (m.type() !== "error" || /play\(\)|NotAllowedError|AbortError/.test(t) || allowed(t)) return;
      errors.push(`console: ${t}`);
    });
    page.on("request", (r) => {
      const u = new URL(r.url());
      if (u.pathname.startsWith("/api/engine/relay")) log.relay.push({ at: Date.now(), what: `${r.method()} ${u.pathname}` });
      if (u.pathname === "/api/engine/health") log.studioHealth.push(Date.now());
    });

    // the studio's site: a passcode set, this session locked
    await ctx.route("**/api/session", (r) => (r.request().method() === "GET" ? r.fulfill({ json: { unlocked: false, required: true } }) : r.fallback()));
    // the fake own engine
    await ctx.route(`${OWN}/**`, async (r) => {
      const req = r.request();
      const u = new URL(req.url());
      const p = u.pathname;
      const h = req.headers();
      log.own.push({ method: req.method(), path: p, auth: h.authorization || "", keys: H.filter((k) => h[k]), at: Date.now() });
      if (state.mode === "down") return r.abort("connectionrefused");
      const cors = { "access-control-allow-origin": origin, vary: "Origin" };
      if (req.method() === "OPTIONS") {
        return r.fulfill({ status: 204, headers: { ...cors, "access-control-allow-methods": "GET, POST", "access-control-allow-headers": "Authorization, Content-Type, X-CBJ-Gemini-Key, X-CBJ-Anthropic-Key, X-CBJ-Planner" } });
      }
      const json = (body, status = 200) => r.fulfill({ status, headers: { ...cors, "content-type": "application/json" }, body: JSON.stringify(body) });
      if (p === "/api/health") return json({ ok: true, busy: false, backend: "claude", models: ["claude-cli/opus"], effort: "low", own_keys: { gemini: false, anthropic: false, planner: "studio" } });
      // every other /api call needs the token, as an engine with CBJ_API_TOKEN does (the 401 carries CORS headers)
      if (p.startsWith("/api/") && !p.startsWith("/api/sprite/") && h.authorization !== `Bearer ${TOKEN}`) {
        return json({ detail: "this engine needs its access token (Authorization: Bearer ...)" }, 401);
      }
      if (p === "/api/meta") return json(meta);
      if (p === "/api/jobs") return json([]);
      if (req.method() === "POST" && p === "/api/enhance") return json(enhance);
      if (req.method() === "POST" && p === "/api/plan") return json({ job: "qa-own-plan" });
      if (p === "/api/jobs/qa-own-plan") {
        return json({ id: "qa-own-plan", kind: "plan", status: "done", stage: "done", lines: [{ t: 0.2, stage: "plan", text: "qa: the plan is answered by the test" }], n_lines: 1, result: brief, elapsed: 1 });
      }
      if (req.method() === "POST" && p === "/api/feedback") {
        const b = req.postDataJSON() || {};
        return json({ id: "fb-qa-own-engine", created: "2026-10-19 12:00:00", designer: b.designer || "", page: b.page, area: b.area, kind: b.kind, wrong: b.wrong, expected: "", rating: null, scene: {} });
      }
      if (req.method() !== "GET") {
        log.aborted.push(`${req.method()} ${p}`);
        return r.abort();
      }
      // reads: served from the studio engine (GET only), as if the user's engine held the same studio
      const res = await r.fetch({ url: `${ENGINE}${p}${u.search}`, headers: { ...engineAuth() } });
      return r.fulfill({ response: res, headers: { ...res.headers(), ...cors } });
    });

    const keyIcon = page.locator('button[aria-label^="Your engine and keys"]').first();
    const dialog = page.getByRole("dialog", { name: "Your engine and keys" });
    const statusPill = page.locator('header [role="status"]').first();
    const enginePill = page.locator('header button[title="Running on your own Claude account"]');
    const lockBtn = page.getByRole("button", { name: /^(Unlock|Unlocked|Unlock the studio|Lock the studio)$/ });
    const urlField = dialog.getByLabel("Engine URL", { exact: true });
    const tokenField = dialog.getByLabel("Engine token (optional)", { exact: true });
    const saveBtn = dialog.getByRole("button", { name: "Save", exact: true });
    const checkBtn = dialog.getByRole("button", { name: "Check", exact: true });
    const stores = () => page.evaluate(() => ({ session: sessionStorage.getItem("cbj.keys"), local: localStorage.getItem("cbj.keys") }));
    async function runCheck() {
      await checkBtn.click();
      await dialog.getByRole("button", { name: "Checking…" }).waitFor({ state: "detached", timeout: 15000 }).catch(() => null);
      await checkBtn.waitFor({ timeout: 15000 });
    }
    // the studio's engine may be busy with someone else's job: online or busy both count as up
    const studioUp = () =>
      page.waitForFunction(() => /^Engine (online|busy)/.test(document.querySelector('header [role="status"]')?.getAttribute("title") || ""), null, { timeout: 15000 }).catch(() => null);
    const alertText = async () => ((await dialog.getByRole("alert").first().innerText().catch(() => "")) || "").replace(/\s+/g, " ");

    // ── the studio's engine first: the lock is there ────────────────────────────────────────────────────
    await page.goto(base + "/", { waitUntil: "load" });
    await studioUp();
    check((await lockBtn.count()) >= 1 && (await enginePill.count()) === 0, `${tag} before: the studio's engine, the Unlock button, no engine pill`);

    // ── the dialog: two modes, own first and recommended ───────────────────────────────────────────────
    await keyIcon.click();
    await dialog.waitFor({ timeout: 5000 });
    const modes = dialog.getByRole("radiogroup", { name: "Which engine runs your work" }).getByRole("radio");
    const ownRadio = dialog.getByRole("radio", { name: /^My own engine \(my Claude CLI, my Gemini key\)/ });
    const studioRadio = dialog.getByRole("radio", { name: "This studio's engine, with my Gemini key" });
    check((await modes.count()) === 2 && (await ownRadio.isChecked()) && (await dialog.getByText("Recommended").count()) === 1, `${tag} two modes, "My own engine" chosen by default and marked Recommended`);
    check(
      (await urlField.getAttribute("placeholder")) === "http://127.0.0.1:8765" && (await tokenField.getAttribute("type")) === "password",
      `${tag} the Engine URL (placeholder http://127.0.0.1:8765) and the token as a password field`,
    );
    const steps = (await dialog.locator("ol li").allInnerTexts()).map((t) => t.replace(/\s+/g, " ").trim());
    check(
      steps.length === 3 &&
        steps[0] === "On your Mac: claude once to log in, then in cbj-creative/.env: CBJ_PLANNER=claude and GEMINI_API_KEY=...; uv run cbj setup-check --live proves it." &&
        steps[1] === `Start it for this site: CBJ_CORS_ORIGINS=${origin} uv run cbj ui` &&
        steps[2] === "Paste the URL here and press Check.",
      `${tag} the three steps ${JSON.stringify(steps)}`,
    );
    check(await saveBtn.isDisabled(), `${tag} Save is disabled before a Check`);
    await shot(page, `dialog-${vpName}`, false);
    check((await overflow(page)) === 0, `${tag} no horizontal overflow with the dialog open`);
    await studioRadio.check();
    const first = "The planner runs on the studio's Claude account. To use your own Claude account, choose My own engine: it runs through your own Claude Code login, no API key.";
    const firstSeen = ((await dialog.locator("p").filter({ hasText: /^The planner runs on the studio's Claude account/ }).first().innerText().catch(() => "")) || "").replace(/\s+/g, " ").trim();
    check(
      firstSeen === first && (await dialog.getByLabel("Gemini API key · reads reference videos on your own quota").count()) === 1 && !(await saveBtn.isDisabled()),
      `${tag} mode B: the first line ("${firstSeen}"), the one Gemini key field, Save enabled`,
    );
    check(
      (await dialog.getByLabel(/Anthropic/).count()) === 0 &&
        (await dialog.getByRole("radio", { name: /planner|Anthropic/ }).count()) === 0 &&
        (await dialog.getByRole("textbox", { name: /Model id/ }).count()) === 0 &&
        (await dialog.getByRole("button", { name: /^claude-/ }).count()) === 0 &&
        !/Anthropic/i.test(await dialog.innerText()),
      `${tag} mode B: no Anthropic key, no planner radios, no model id or chips, the word "Anthropic" nowhere in the dialog`,
    );
    await shot(page, `dialog-studio-${vpName}`, false);
    await ownRadio.check();

    // ── the three failures ─────────────────────────────────────────────────────────────────────────────
    state.tolerate = true;
    await urlField.fill("127.0.0.1:8765/");
    state.mode = "down";
    await runCheck();
    let a = await alertText();
    check(/^Not reachable: nothing answered at http:\/\/127\.0\.0\.1:8765\. Is uv run cbj ui running on your Mac\?/.test(a) && (await saveBtn.isDisabled()), `${tag} not reachable: "${a.slice(0, 90)}…", Save disabled`);
    check((await urlField.inputValue()) === OWN, `${tag} the address is shown as it will be used (${await urlField.inputValue()})`);
    state.mode = "ok";
    await urlField.fill(NOCORS);
    await runCheck();
    a = await alertText();
    check(a === `Blocked by CORS: the engine answered but does not allow this site. Start it with CBJ_CORS_ORIGINS=${origin} uv run cbj ui.` && (await saveBtn.isDisabled()), `${tag} CORS blocked: "${a}"`);
    await shot(page, `check-cors-${vpName}`, false);
    await urlField.fill(OWN);
    await tokenField.fill("wrong-token");
    await runCheck();
    a = await alertText();
    check(a.startsWith("Wrong token (401)") && (await saveBtn.isDisabled()), `${tag} wrong token: "${a.slice(0, 60)}…", Save disabled`);
    state.tolerate = false;

    // ── success, Save ──────────────────────────────────────────────────────────────────────────────────
    await tokenField.fill(TOKEN);
    check(await saveBtn.isDisabled(), `${tag} a changed token needs a new Check`);
    await runCheck();
    const okLine = (await dialog.getByRole("status").first().innerText()).trim();
    check(okLine === "Reachable · planner: claude-cli/opus · voice: yes" && !(await saveBtn.isDisabled()), `${tag} Check: "${okLine}", Save enabled`);
    const checkCalls = log.own.filter((c) => c.path === "/api/meta").at(-1);
    check(checkCalls?.auth === `Bearer ${TOKEN}`, `${tag} Check sends the token as Bearer on /api/meta`);
    await shot(page, `checked-${vpName}`, false);
    await urlField.fill(`${OWN}/x`);
    check(await saveBtn.isDisabled(), `${tag} a changed URL needs a new Check`);
    await urlField.fill(OWN);
    check(!(await saveBtn.isDisabled()), `${tag} back to the checked URL: Save enabled again`);
    const remember = vpName === "390";
    if (remember) await dialog.getByRole("switch", { name: "Remember on this device" }).click();
    await saveBtn.click();
    await dialog.waitFor({ state: "detached", timeout: 5000 });
    const saveAt = Date.now();
    const st = await stores();
    const saved = JSON.parse((remember ? st.local : st.session) || "{}");
    check(saved.engine?.url === OWN && saved.engine?.token === TOKEN && (remember ? st.session === null : st.local === null), `${tag} saved in ${remember ? "localStorage (Remember on)" : "sessionStorage (this tab)"}: ${JSON.stringify(saved.engine)}`);

    // ── the whole site on the own engine ───────────────────────────────────────────────────────────────
    await statusPill.filter({ hasText: "Online" }).waitFor({ timeout: 10000 });
    await page.waitForFunction(() => /claude-cli\/opus · your engine/.test(document.body.textContent || ""), null, { timeout: 10000 }).catch(() => null);
    check((await statusPill.getAttribute("title")) === "Your engine online", `${tag} the status pill: "${await statusPill.getAttribute("title")}" (shows "${(await statusPill.innerText()).trim()}")`);
    if (vpName === "1440") {
      check((await statusPill.innerText()).trim() === "Your engine online", `${tag} the status pill reads "Your engine online"`);
      check((await enginePill.innerText()).trim() === "Your engine: 127.0.0.1:8765 · claude-cli/opus", `${tag} the header pill: "${(await enginePill.innerText()).trim()}" (tooltip "Running on your own Claude account")`);
    } else {
      const label = (await keyIcon.getAttribute("aria-label")) || "";
      check(!(await enginePill.isVisible()) && label.includes("127.0.0.1:8765 · claude-cli/opus"), `${tag} at 390 the pill folds into the key icon ("${label}")`);
    }
    check((await lockBtn.count()) === 0, `${tag} the lock button is hidden (no passcode needed)`);
    const eyebrow = (await page.getByText(/^Planner: /).first().textContent()).trim();
    check(eyebrow === "Planner: claude-cli/opus · your engine · one job at a time", `${tag} Create's planner line: "${eyebrow}"`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, `header-${vpName}`, false);

    // a POST: Enhance goes to the own URL with the token, not through the relay, and asks no passcode
    await page.fill("#prompt", "Zor bir seviye yap, 45 saniye.");
    await page.getByRole("button", { name: /Enhance prompt/ }).click();
    await page.getByRole("region", { name: "Enhanced request" }).waitFor({ timeout: 10000 });
    const enh = log.own.filter((c) => c.method === "POST" && c.path === "/api/enhance");
    check(enh.length === 1 && enh[0].auth === `Bearer ${TOKEN}` && enh[0].keys.length === 0, `${tag} POST /api/enhance went to ${OWN} with the token, no X-CBJ key headers`);
    check((await page.getByRole("dialog", { name: "Unlock the studio" }).count()) === 0, `${tag} no passcode asked for Enhance`);
    // one job: Plan only → POST /api/plan and its polls on the own engine
    await page.getByRole("button", { name: "Plan only" }).click();
    await page.getByRole("button", { name: "Make it" }).waitFor({ timeout: 15000 });
    const plan = log.own.filter((c) => c.path === "/api/plan" || c.path.startsWith("/api/jobs/qa-own-plan"));
    check(plan.some((c) => c.method === "POST") && plan.some((c) => c.method === "GET") && plan.every((c) => c.auth === `Bearer ${TOKEN}`), `${tag} the plan job: POST and polls on the own engine with the token (${plan.length})`);
    await shot(page, `create-${vpName}`);
    check((await overflow(page)) === 0, `${tag} Create: no horizontal overflow`);

    // one feedback POST, from the header, without the passcode
    await page.getByRole("button", { name: "Feedback about the studio" }).click();
    const fdlg = page.locator("dialog[open]");
    await fdlg.getByLabel("What happened?").fill("qa: own engine feedback");
    await fdlg.getByRole("button", { name: "Send", exact: true }).click();
    await fdlg.getByText(/^Thanks — saved as fb-qa-own-engine/).waitFor({ timeout: 10000 }).catch(() => null);
    const fb = log.own.filter((c) => c.method === "POST" && c.path === "/api/feedback");
    check(fb.length === 1 && fb[0].auth === `Bearer ${TOKEN}` && (await fdlg.getByText(/^Thanks — saved as fb-qa-own-engine/).count()) === 1, `${tag} POST /api/feedback on the own engine, the thanks line`);
    await fdlg.getByText("Close", { exact: true }).click();

    // media on the own host (the Edit workspace)
    await page.goto(`${base}/edit?c=${CID}&v=13`, { waitUntil: "load" });
    await page.getByText("What changed").first().waitFor({ timeout: 20000 });
    await page.waitForTimeout(1500);
    const media = await page.evaluate(() =>
      [...document.querySelectorAll("video[src], video[poster], source[src], img[src]")].flatMap((el) => [el.getAttribute("src"), el.getAttribute("poster")]).filter((s) => s && /\/studio\/|\/showcase\//.test(s)),
    );
    check(media.length > 0 && media.every((s) => s.startsWith(`${OWN}/studio/`)), `${tag} media src on the own host (${media.length}: ${media[0]})`);
    const vid = await page.locator("video").first().getAttribute("src").catch(() => null);
    check(Boolean(vid?.startsWith(`${OWN}/studio/`)), `${tag} the player's <video> plays from ${OWN}/studio/ (${vid})`);
    await shot(page, `edit-${vpName}`);
    check((await overflow(page)) === 0, `${tag} Edit: no horizontal overflow`);

    // the owner's page without the passcode
    await page.goto(`${base}/feedback`, { waitUntil: "load" });
    await page.getByRole("tab").first().waitFor({ timeout: 15000 }).catch(() => null);
    check((await page.getByRole("tab").count()) >= 2 && (await page.getByText("This page is for the studio's owner.").count()) === 0, `${tag} /feedback: the owner's tabs, no passcode card`);
    check(log.own.some((c) => c.path === "/api/feedback" && c.method === "GET"), `${tag} /feedback read the records from the own engine`);
    await shot(page, `feedback-${vpName}`);
    check((await overflow(page)) === 0, `${tag} /feedback: no horizontal overflow`);

    const relayed = log.relay.filter((x) => x.at > saveAt).map((x) => x.what);
    check(relayed.length === 0, `${tag} nothing went through the relay since Save, page loads included${relayed.length ? ": " + relayed.join(", ") : ""}`);
    const polled = log.studioHealth.filter((t) => t > saveAt + 500).length;
    check(polled === 0, `${tag} the studio's health was not polled while the own engine is on, page loads included (${polled})`);
    check(log.own.every((c) => c.keys.length === 0), `${tag} no X-CBJ key header ever went to the own engine`);
    check(log.aborted.length === 0, `${tag} no other POST was attempted (${log.aborted.join(", ")})`);

    // ── offline mid-session: the setting stays ────────────────────────────────────────────────────────
    await page.goto(base + "/", { waitUntil: "load" });
    await statusPill.filter({ hasText: "Online" }).waitFor({ timeout: 10000 });
    state.tolerate = true;
    state.mode = "down";
    const off = await page
      .waitForFunction(() => document.querySelector('header [role="status"]')?.getAttribute("title") === "Your engine offline: check uv run cbj ui", null, { timeout: 15000 })
      .then(() => true, () => false);
    const kept = JSON.parse(((await stores())[remember ? "local" : "session"]) || "{}");
    check(off && kept.engine?.url === OWN, `${tag} offline mid-session: "Your engine offline: check uv run cbj ui", the setting kept`);
    check((await page.getByText(/Your engine is offline right now/).count()) === 1, `${tag} offline: the banner names your engine`);
    if (vpName === "1440") check((await statusPill.innerText()).trim() === "Your engine offline: check uv run cbj ui", `${tag} offline pill text`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, `offline-${vpName}`, false);
    state.mode = "ok";
    const back = await page
      .waitForFunction(() => document.querySelector('header [role="status"]')?.getAttribute("title") === "Your engine online", null, { timeout: 15000 })
      .then(() => true, () => false);
    check(back, `${tag} back online on the next poll`);
    state.tolerate = false;

    // ── Clear: back to the studio's engine and its passcode ────────────────────────────────────────────
    await keyIcon.click();
    await dialog.waitFor();
    await dialog.getByRole("status").filter({ hasText: /^Reachable/ }).first().waitFor({ timeout: 10000 }).catch(() => null);
    check((await urlField.inputValue()) === OWN && !(await saveBtn.isDisabled()), `${tag} reopened: the saved engine, checked again on open`);
    await dialog.getByRole("button", { name: "Clear" }).click();
    await dialog.getByText("Back to the studio's engine.").waitFor({ timeout: 5000 });
    const cleared = await stores();
    check(cleared.local === null && cleared.session === null, `${tag} Clear empties both stores`);
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await studioUp();
    check(/^Engine (online|busy)/.test((await statusPill.getAttribute("title")) || "") && (await enginePill.count()) === 0 && (await lockBtn.count()) >= 1, `${tag} Clear: the studio's engine again ("${await statusPill.getAttribute("title")}"), no engine pill, the lock back`);
    const line = (await page.getByText(/^Planner: /).first().textContent()).trim();
    check(!line.includes("your engine"), `${tag} Clear: Create's planner line is the studio's ("${line}")`);
    await page.fill("#prompt", "An easy level.");
    const enhBefore = log.own.length;
    await page.getByRole("button", { name: /Enhance prompt/ }).click();
    const unlock = page.getByRole("dialog", { name: "Unlock the studio" });
    const gated = await unlock.waitFor({ timeout: 5000 }).then(() => true, () => false);
    check(gated && log.own.length === enhBefore, `${tag} Clear: Enhance asks for the passcode again, nothing sent to the own engine`);
    if (gated) await unlock.getByRole("button", { name: "Cancel" }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, `cleared-${vpName}`, false);

    // ── 1440: the switch back by saving "This studio's engine, with my Gemini key"; the Unlock dialog's way in ──
    if (vpName === "1440") {
      await page.getByRole("button", { name: /^(Unlock|Unlock the studio)$/ }).first().click();
      await unlock.waitFor();
      const link = unlock.getByRole("button", { name: "Optional: use your own engine or your own Gemini key", exact: true });
      check((await link.count()) === 1, `${tag} the Unlock dialog's link: "Optional: use your own engine or your own Gemini key"`);
      await link.click();
      await dialog.waitFor();
      await urlField.fill(OWN);
      await tokenField.fill(TOKEN);
      await urlField.press("Enter");
      await dialog.getByRole("status").filter({ hasText: /^Reachable/ }).first().waitFor({ timeout: 10000 });
      check(!(await saveBtn.isDisabled()), `${tag} from the Unlock dialog: Enter in the URL field runs Check`);
      await saveBtn.click();
      await dialog.waitFor({ state: "detached" });
      await page.waitForTimeout(400);
      check((await unlock.count()) === 0, `${tag} saving an own engine closes the Unlock dialog (no passcode needed)`);
      await enginePill.waitFor({ timeout: 10000 });
      await keyIcon.click();
      await dialog.waitFor();
      await studioRadio.check();
      await saveBtn.click();
      await dialog.waitFor({ state: "detached" });
      await studioUp();
      const st2 = await stores();
      check(!st2.session && !st2.local && (await enginePill.count()) === 0 && (await lockBtn.count()) >= 1, `${tag} saving "This studio's engine" switches back (no engine stored, the lock back)`);
    }

    check(errors.length === 0, `${tag} no unexpected page/console errors ${errors.join("; ")}`);
    await ctx.close();
  }
  plain.close();
}
