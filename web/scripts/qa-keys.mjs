// SPEC-OWN-KEYS §4 and SPEC-OWN-ENGINE-2, run from qa.mjs (it passes the browser and its check()); `--keys-only` runs
// just these. No real key goes anywhere and no job starts: the one value is an obvious fake ("test-gemini-key"), GET
// /api/meta is answered here the way the engine would (own_keys from the headers it gets), POST /api/plan and its job
// are answered here, and any other workflow POST is aborted before the engine.
// Since SPEC-OWN-ENGINE-2 the site asks for no Anthropic key: the dialog's second mode ("This studio's engine, with my
// Gemini key") has one field, and only X-CBJ-Gemini-Key is ever sent (never X-CBJ-Anthropic-Key or X-CBJ-Planner).
// Browser: the dialog from the header and from the Unlock dialog (a locked session answered here), Save to this tab
// (sessionStorage only), Remember (localStorage only), the one header on POST /api/plan and GET /api/meta and none on
// GET /api/creatives or the job polls, the header pill ("Your Gemini key") and Create's planner line, a record an older
// site version stored with an Anthropic key (never sent, dropped on the next save), Clear (both stores empty, the pill
// gone), an older engine (no features.own_keys: no header sent, the dialog says the key stays unsent) and offline (the
// icon still opens the dialog: its first mode, "My own engine", needs no studio engine).
// 1440 and 390, no horizontal overflow, no page or console errors; screenshots qa/keys-*.
// Relay (§3): a second `next start` on :3106 pointed at a recording stand-in engine on :8799 (never the real one): the
// relay's forwarded-header list is unchanged (SPEC-OWN-ENGINE-2 §2 leaves it as is): the three headers are forwarded on
// POSTs and GET api/meta only; the passcode check still applies. Skip with --no-relay.
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { engineJson } from "./qa-engine.mjs";

const FAKE = { gemini: "test-gemini-key" };
const HONEST =
  "Your key is used only for the reference-video reads of your own jobs, held in the engine's memory while the job runs, and never stored or logged by it. The passcode is still needed: the studio's computer still records the game.";
const H = ["x-cbj-gemini-key", "x-cbj-anthropic-key", "x-cbj-planner"];
const WORKFLOW = /\/api\/(plan|make|preview|review|direct|upload|enhance|trends|feedback|lessons|soundtrack)(\/|$)/;
const MODE_B = "This studio's engine, with my Gemini key";
const FIELD = "Gemini API key · reads reference videos on your own quota";

export default async function keysChecks({ browser, base, label, check, featurePage, VIEWPORTS, CID, relay = true }) {
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const shot = async (page, file, full = true) => {
    await page.waitForTimeout(400);
    await page.screenshot({ path: `qa/${file}`, fullPage: full, scale: "css" }); // a modal <dialog>: the viewport (full = false)
  };
  const noErrors = (errors, what) => check(errors.length === 0, `${what}: no page/console errors ${errors.join("; ")}`);
  const stores = (page) =>
    page.evaluate(() => ({ session: sessionStorage.getItem("cbj.keys"), local: localStorage.getItem("cbj.keys") }));
  const keyIcon = (page) => page.locator('button[aria-label^="Your engine and keys"]').first();
  const dialog = (page) => page.getByRole("dialog", { name: "Your engine and keys" });
  /** The key is the dialog's second mode: choose it (a dialog that saved a key opens on it already). */
  const keysMode = (page) => dialog(page).getByRole("radio", { name: MODE_B }).check();
  const pill = (page) => page.locator('header button[title="Running on your own Gemini key"]');
  const own = (headers) => H.filter((h) => headers[h]);
  /** Only the Gemini key: never the Anthropic key or a planner. */
  const onlyGemini = (h) => h["x-cbj-gemini-key"] === FAKE.gemini && !h["x-cbj-anthropic-key"] && !h["x-cbj-planner"];

  const versions = await engineJson(`/api/creatives/${CID}`);
  const brief = versions.find((x) => x.n === 1).brief; // the plan job is answered with v1's real brief

  /** Every engine request's own-key headers, meta answered like the engine, plan answered, other workflow POSTs aborted. */
  async function wire(page, { ownKeysFeature = true, locked = false, offline = false } = {}) {
    const log = { meta: [], plan: [], reads: [], aborted: [] };
    page.on("request", (r) => {
      const u = new URL(r.url());
      if (r.method() === "GET" && /\/api\/(creatives|jobs)(\/|$)/.test(u.pathname)) log.reads.push({ path: u.pathname, own: own(r.headers()) });
    });
    await page.route("**/api/**", (r) => {
      const req = r.request();
      const p = new URL(req.url()).pathname;
      if (req.method() === "POST" && WORKFLOW.test(p) && !p.endsWith("/api/plan")) {
        log.aborted.push(p);
        return r.abort();
      }
      return r.fallback();
    });
    if (offline) await page.route("**/api/engine/health", (r) => r.fulfill({ json: { online: false, url: "" } }));
    // the studio engine may be busy with someone else's job: answered as idle, so Plan only stays enabled (its plan is answered here)
    else await page.route("**/api/engine/health", async (r) => r.fulfill({ json: { ...(await (await r.fetch()).json()), busy: false } }));
    if (locked) await page.route("**/api/session", (r) => (r.request().method() === "GET" ? r.fulfill({ json: { unlocked: false, required: true } }) : r.fallback()));
    await page.route("**/api/meta", async (r) => {
      const h = r.request().headers();
      log.meta.push({ path: new URL(r.request().url()).pathname, headers: Object.fromEntries(H.map((k) => [k, h[k]])) });
      const real = await (await r.fetch()).json();
      const features = { ...(real.features || {}) };
      if (ownKeysFeature) features.own_keys = true;
      else delete features.own_keys;
      if (!ownKeysFeature) return r.fulfill({ json: { ...real, own_keys: undefined, features } });
      return r.fulfill({ json: { ...real, own_keys: { gemini: Boolean(h["x-cbj-gemini-key"]), anthropic: false, planner: "studio" }, features } });
    });
    await page.route("**/api/plan", (r) => {
      log.plan.push(Object.fromEntries(H.map((k) => [k, r.request().headers()[k]])));
      return r.fulfill({ json: { job: "qa-keys-plan" } });
    });
    await page.route("**/api/jobs/qa-keys-plan*", (r) =>
      r.fulfill({ json: { id: "qa-keys-plan", kind: "plan", status: "done", stage: "done", lines: [{ t: 0.2, stage: "plan", text: "qa: the plan is answered by the test" }], n_lines: 1, result: brief, elapsed: 1 } }),
    );
    return log;
  }

  async function fillAndSave(page, { remember }) {
    const d = dialog(page);
    await keysMode(page);
    await d.getByLabel(FIELD).fill(`  ${FAKE.gemini} `); // trimmed on save
    const sw = d.getByRole("switch", { name: "Remember on this device" });
    if (((await sw.getAttribute("aria-checked")) === "true") !== remember) await sw.click();
    await d.getByRole("button", { name: "Save", exact: true }).click();
    await d.waitFor({ state: "detached", timeout: 10000 });
  }

  if (label === "offline") return; // the offline state is answered here below, from an online run

  for (const [vpName, vp] of VIEWPORTS) {
    const tag = `${vpName} keys:`;

    // ── header: open, the words, the one field, save to this tab, the header, the pill ────────────────────
    {
      const { ctx, page, errors } = await featurePage(vp);
      const log = await wire(page);
      await page.goto(base + "/", { waitUntil: "load" });
      await page.locator('[role="status"]').filter({ hasText: "Online" }).first().waitFor({ timeout: 15000 });
      await page.waitForFunction(() => document.querySelector('button[aria-label^="Your engine and keys"]'), null, { timeout: 15000 });
      await page.waitForTimeout(800); // meta: the engine says it takes keys
      check((await keyIcon(page).isEnabled()) && (await pill(page).count()) === 0, `${tag} the key icon is enabled, no pill before any key`);
      check(log.meta.length >= 1 && log.meta.every((m) => own(m.headers).length === 0), `${tag} GET /api/meta carries no key headers before any key is set`);
      await keyIcon(page).click();
      const d = dialog(page);
      await d.waitFor({ timeout: 5000 });
      check(await d.getByRole("radio", { name: /^My own engine/ }).isChecked(), `${tag} the dialog opens on "My own engine" (the default)`);
      await keysMode(page);
      const firstLine = ((await d.locator("p").filter({ hasText: /^The planner runs on the studio's Claude account/ }).first().innerText()) || "").replace(/\s+/g, " ").trim();
      check(
        firstLine === "The planner runs on the studio's Claude account. To use your own Claude account, choose My own engine: it runs through your own Claude Code login, no API key.",
        `${tag} mode B's first line ("${firstLine}")`,
      );
      check((await d.getByText(HONEST, { exact: true }).count()) === 1, `${tag} the honesty line, verbatim`);
      check((await d.getByLabel(FIELD).getAttribute("type")) === "password" && (await d.locator("input:not([type=radio])").count()) === 1, `${tag} one field, the Gemini key, a password field`);
      check(
        (await d.getByLabel(/Anthropic/).count()) === 0 &&
          (await d.getByRole("radio", { name: /planner|Anthropic/ }).count()) === 0 &&
          (await d.getByRole("textbox", { name: /Model id/ }).count()) === 0 &&
          (await d.getByRole("button", { name: /^claude-/ }).count()) === 0 &&
          !/Anthropic/i.test(await d.innerText()),
        `${tag} no Anthropic key, no planner radios, no model id or chips`,
      );
      check((await d.getByRole("switch", { name: "Remember on this device" }).getAttribute("aria-checked")) === "false", `${tag} Remember is off by default (this tab)`);
      await d.getByLabel(FIELD).fill(FAKE.gemini);
      await d.getByRole("button", { name: "Show the Gemini API key" }).click();
      check((await d.getByLabel(FIELD).getAttribute("type")) === "text", `${tag} Show reveals the Gemini key`);
      await d.getByRole("button", { name: "Hide the Gemini API key" }).click();
      check((await d.getByLabel(FIELD).getAttribute("type")) === "password", `${tag} Hide masks it again`);
      await shot(page, `keys-dialog-${vpName}.png`, false);
      check((await overflow(page)) === 0, `${tag} no horizontal overflow with the dialog open`);
      await d.getByRole("button", { name: "Cancel" }).click();
      await d.waitFor({ state: "detached" });
      check((await stores(page)).session === null, `${tag} nothing stored after Cancel`);

      // save to this tab
      const metaBefore = log.meta.length;
      await keyIcon(page).click();
      await dialog(page).waitFor();
      await fillAndSave(page, { remember: false });
      const st = await stores(page);
      const saved = st.session ? JSON.parse(st.session) : {};
      check(saved.gemini === FAKE.gemini && st.local === null, `${tag} Save (this tab): sessionStorage has the key (trimmed), localStorage does not`);
      check(Object.keys(saved).join(",") === "gemini", `${tag} the stored record holds the Gemini key only (${Object.keys(saved).join(",")})`);
      await page.waitForTimeout(500);
      const metaAfter = log.meta.slice(metaBefore);
      const m = metaAfter.at(-1)?.headers || {};
      check(metaAfter.length >= 1 && onlyGemini(m), `${tag} after Save, GET /api/meta carries X-CBJ-Gemini-Key only`);
      if (vpName === "1440") {
        await pill(page).waitFor({ timeout: 5000 });
        check((await pill(page).innerText()).trim() === "Your Gemini key", `${tag} the header pill says "Your Gemini key" (${await pill(page).innerText()})`);
      } else {
        check(!(await pill(page).isVisible()) && /running on your own Gemini key/.test((await keyIcon(page).getAttribute("aria-label")) || ""), `${tag} at 390 the pill folds into the key icon (its label and dot)`);
      }
      const eyebrow = (await page.getByText(/^Planner: /).first().textContent()).trim(); // textContent: the line is uppercased by CSS
      check(/^Planner: .+ · your Gemini key · one job at a time$/.test(eyebrow) && !/anthropic/i.test(eyebrow), `${tag} Create's planner line: "${eyebrow}"`);

      await page.evaluate(() => window.scrollTo(0, 0));
      await shot(page, `keys-pill-${vpName}.png`, false); // the top of the page: the header with the pill (or the dotted icon)
      // the header on POST /api/plan, none on the reads
      await page.fill("#prompt", "An easy level, calm, 30 seconds.");
      await page.getByRole("button", { name: "Plan only" }).click();
      await page.getByRole("button", { name: "Make it" }).waitFor({ timeout: 15000 });
      const p = log.plan.at(-1) || {};
      check(log.plan.length === 1 && onlyGemini(p), `${tag} POST /api/plan carries X-CBJ-Gemini-Key only`);
      const creatives = log.reads.filter((r) => r.path.endsWith("/api/creatives"));
      check(creatives.length >= 1 && creatives.every((r) => r.own.length === 0), `${tag} GET /api/creatives carries no key headers (${creatives.length} read)`);
      const jobs = log.reads.filter((r) => r.path.includes("/api/jobs/"));
      check(jobs.length >= 1 && jobs.every((r) => r.own.length === 0), `${tag} the job polls carry no key headers (${jobs.length})`);
      check(!page.url().includes(FAKE.gemini), `${tag} no key in the page URL`);
      await shot(page, `keys-header-pill-${vpName}.png`);
      check((await overflow(page)) === 0, `${tag} no horizontal overflow with the pill`);

      // the dialog opens with the saved key, on mode B
      await (vpName === "1440" ? pill(page) : keyIcon(page)).click();
      await dialog(page).waitFor();
      check((await dialog(page).getByRole("radio", { name: MODE_B }).isChecked()) && (await dialog(page).getByLabel(FIELD).inputValue()) === FAKE.gemini, `${tag} the dialog opens on mode B with the saved key`);
      await dialog(page).getByRole("button", { name: "Cancel" }).click();
      check(log.aborted.length === 0, `${tag} no other workflow POST was attempted`);
      check(log.meta.every((x) => !x.headers["x-cbj-anthropic-key"] && !x.headers["x-cbj-planner"]), `${tag} no X-CBJ-Anthropic-Key or X-CBJ-Planner on any meta call`);
      noErrors(errors, `${tag} header`);
      await ctx.close();
    }

    // ── a record an older site stored (an Anthropic key, its planner): never sent, dropped on the next save ──
    {
      const { ctx, page, errors } = await featurePage(vp);
      await ctx.addInitScript(() => {
        if (!sessionStorage.getItem("qa-seeded")) {
          sessionStorage.setItem("qa-seeded", "1");
          sessionStorage.setItem("cbj.keys", JSON.stringify({ gemini: "test-gemini-key", anthropic: "test-anthropic-key", planner: "anthropic", model: "claude-sonnet-5-5" }));
        }
      });
      const log = await wire(page);
      await page.goto(base + "/", { waitUntil: "load" });
      await page.waitForFunction(() => document.querySelector('button[aria-label^="Your engine and keys"]'), null, { timeout: 15000 });
      await page.waitForTimeout(1500);
      check(log.meta.length >= 1 && log.meta.every((x) => !x.headers["x-cbj-anthropic-key"] && !x.headers["x-cbj-planner"]) && log.meta.some((x) => onlyGemini(x.headers)), `${tag} an old record: meta carries the Gemini key only, never the stored Anthropic key`);
      await keyIcon(page).click();
      await dialog(page).waitFor();
      await dialog(page).getByRole("button", { name: "Save", exact: true }).click();
      await dialog(page).waitFor({ state: "detached" });
      const saved = JSON.parse((await stores(page)).session || "{}");
      check(Object.keys(saved).join(",") === "gemini", `${tag} an old record: saved again it keeps the Gemini key only (${Object.keys(saved).join(",")})`);
      noErrors(errors, `${tag} old record`);
      await ctx.close();
    }

    // ── Remember, reload, Clear ───────────────────────────────────────────────────────────────────────
    {
      const { ctx, page, errors } = await featurePage(vp);
      const log = await wire(page);
      await page.goto(base + "/", { waitUntil: "load" });
      await page.waitForFunction(() => document.querySelector('button[aria-label^="Your engine and keys"]'), null, { timeout: 15000 });
      await page.waitForTimeout(800);
      await keyIcon(page).click();
      await dialog(page).waitFor();
      await fillAndSave(page, { remember: true });
      let st = await stores(page);
      check(st.local !== null && JSON.parse(st.local).gemini === FAKE.gemini && st.session === null, `${tag} Remember on: localStorage has the key, sessionStorage does not`);
      await keyIcon(page).click();
      await dialog(page).getByRole("switch", { name: "Remember on this device" }).click();
      await dialog(page).getByRole("button", { name: "Save", exact: true }).click();
      await dialog(page).waitFor({ state: "detached" });
      st = await stores(page);
      check(st.session !== null && st.local === null, `${tag} Remember off again: back to sessionStorage only`);
      await keyIcon(page).click();
      await dialog(page).getByRole("switch", { name: "Remember on this device" }).click();
      await dialog(page).getByRole("button", { name: "Save", exact: true }).click();
      await dialog(page).waitFor({ state: "detached" });
      // a reload: the remembered key is read again and rides on the second meta call (once the engine says it takes it)
      const before = log.meta.length;
      await page.reload({ waitUntil: "load" });
      await page.waitForFunction(() => document.querySelector('button[aria-label^="Your engine and keys"]'), null, { timeout: 15000 });
      await page.waitForTimeout(1600);
      const after = log.meta.slice(before);
      check(after.length >= 2 && own(after[0].headers).length === 0 && onlyGemini(after.at(-1).headers), `${tag} after a reload: meta first without the key (feature unknown), then with it`);
      if (vpName === "1440") check((await pill(page).count()) === 1, `${tag} the pill is back after the reload (remembered)`);
      // Clear
      await keyIcon(page).click();
      const d = dialog(page);
      await d.getByRole("button", { name: "Clear" }).click();
      await d.getByText("Cleared: this browser holds no keys now.").waitFor({ timeout: 5000 });
      st = await stores(page);
      check(st.local === null && st.session === null, `${tag} Clear empties both stores`);
      check((await d.getByLabel(FIELD).inputValue()) === "", `${tag} Clear empties the field`);
      await page.waitForTimeout(300);
      check((await pill(page).count()) === 0, `${tag} Clear: the pill goes`);
      check(own(log.meta.at(-1).headers).length === 0, `${tag} Clear: meta asked again without the key`);
      await shot(page, `keys-cleared-${vpName}.png`, false);
      await d.getByRole("button", { name: "Cancel" }).click();
      const line = (await page.getByText(/^Planner: /).first().textContent()).trim();
      check(/^Planner: [^·]+ · one job at a time$/.test(line), `${tag} Clear: Create's planner line is the studio's again ("${line}")`);
      noErrors(errors, `${tag} remember`);
      await ctx.close();
    }

    // ── from the Unlock dialog (a locked session, answered here): the relay path ──────────────────────────
    {
      const { ctx, page, errors } = await featurePage(vp);
      const log = await wire(page, { locked: true });
      await page.goto(base + "/", { waitUntil: "load" });
      await page.waitForFunction(() => document.querySelector('button[aria-label^="Your engine and keys"]'), null, { timeout: 15000 });
      await page.waitForTimeout(800);
      await page.getByRole("button", { name: /Unlock the studio|^Unlock$/ }).first().click();
      const unlock = page.getByRole("dialog", { name: "Unlock the studio" });
      await unlock.waitFor({ timeout: 5000 });
      const link = unlock.getByRole("button", { name: "Optional: use your own engine or your own Gemini key", exact: true });
      check((await link.count()) === 1, `${tag} the Unlock dialog offers "Optional: use your own engine or your own Gemini key"`);
      await link.click();
      await dialog(page).waitFor({ timeout: 5000 });
      check((await unlock.isVisible()) && (await dialog(page).isVisible()), `${tag} "Your engine and keys" opens over the Unlock dialog`);
      await shot(page, `keys-unlock-${vpName}.png`, false);
      const before = log.meta.length;
      await fillAndSave(page, { remember: false });
      await page.waitForTimeout(500);
      check(await unlock.isVisible(), `${tag} after Save the Unlock dialog is still there (the passcode is still needed)`);
      const m = log.meta.slice(before).at(-1);
      check(m && m.path === "/api/engine/relay/api/meta" && onlyGemini(m.headers), `${tag} locked: GET meta goes through the relay with X-CBJ-Gemini-Key only`);
      check((await stores(page)).session !== null, `${tag} saved from the Unlock dialog (this tab)`);
      await unlock.getByRole("button", { name: "Cancel" }).click();
      check(log.aborted.length === 0 && log.plan.length === 0, `${tag} locked: no workflow POST`);
      noErrors(errors, `${tag} unlock`);
      await ctx.close();
    }

    // ── an older engine (no features.own_keys): the key kept but never sent, the dialog says so ──────────
    {
      const { ctx, page, errors } = await featurePage(vp);
      await ctx.addInitScript((k) => sessionStorage.setItem("cbj.keys", JSON.stringify(k)), FAKE);
      const log = await wire(page, { ownKeysFeature: false });
      await page.goto(base + "/", { waitUntil: "load" });
      await page.locator('[role="status"]').filter({ hasText: "Online" }).first().waitFor({ timeout: 15000 });
      await page.waitForTimeout(1500);
      check((await pill(page).count()) === 0, `${tag} older engine: no pill`);
      await keyIcon(page).click();
      await dialog(page).waitFor();
      check((await dialog(page).getByText(/does not take your own key right now: a key saved here stays in this browser, unsent/).count()) === 1, `${tag} older engine: mode B says the key stays unsent`);
      await dialog(page).getByRole("button", { name: "Cancel" }).click();
      await page.fill("#prompt", "An easy level, calm, 30 seconds.");
      await page.getByRole("button", { name: "Plan only" }).click();
      await page.getByRole("button", { name: "Make it" }).waitFor({ timeout: 15000 });
      check(log.plan.length === 1 && H.every((h) => !log.plan[0][h]) && log.meta.every((m) => own(m.headers).length === 0), `${tag} older engine: no key headers on POST /api/plan or GET /api/meta`);
      noErrors(errors, `${tag} older engine`);
      await ctx.close();
    }

    // ── offline: the icon still opens the dialog, on "My own engine" ───────────────────────────────────────
    {
      const { ctx, page, errors } = await featurePage(vp);
      await wire(page, { offline: true });
      await page.goto(base + "/", { waitUntil: "load" });
      await page.locator('[role="status"]').filter({ hasText: /Offline/ }).first().waitFor({ timeout: 15000 });
      await keyIcon(page).click();
      await dialog(page).waitFor({ timeout: 5000 });
      check((await dialog(page).getByRole("radio", { name: /^My own engine/ }).isChecked()) && (await dialog(page).getByLabel("Engine URL", { exact: true }).count()) === 1, `${tag} offline: the key icon opens the dialog on "My own engine"`);
      await dialog(page).getByRole("button", { name: "Cancel" }).click();
      check((await overflow(page)) === 0, `${tag} offline: no horizontal overflow`);
      await shot(page, `keys-offline-${vpName}.png`);
      noErrors(errors, `${tag} offline`);
      await ctx.close();
    }

    // ── the help sheet's "Your own account" ────────────────────────────────────────────────────────────
    {
      const { ctx, page, errors } = await featurePage(vp);
      await wire(page);
      await page.goto(base + "/", { waitUntil: "load" });
      await page.getByRole("button", { name: "Help" }).first().click();
      const help = page.getByRole("dialog", { name: "How it works" });
      await help.waitFor({ timeout: 5000 });
      const sec = help.locator("section").filter({ has: page.getByRole("heading", { name: "Your own account" }) });
      const items = (await sec.locator("ol li").allInnerTexts()).map((t) => t.replace(/\s+/g, " ").trim());
      check(
        (await sec.count()) === 1 && items.length === 3 && items[0].startsWith("On your Mac: claude once to log in") && items[1].startsWith("Start it for this site: CBJ_CORS_ORIGINS=") && /Gemini key/.test(await sec.innerText()) && !/Anthropic/i.test(await help.innerText()),
        `${tag} the help sheet: "Your own account" with the three steps and the Gemini line, no Anthropic`,
      );
      await sec.scrollIntoViewIfNeeded();
      await shot(page, `keys-help-${vpName}.png`, false);
      noErrors(errors, `${tag} help`);
      await ctx.close();
    }
  }

  if (relay && /localhost|127\.0\.0\.1/.test(base)) await relayChecks(check);
}

/** §3 on the real relay code: a second `next start` (this build) pointed at a recording stand-in engine. */
async function relayChecks(check) {
  const seen = [];
  const fake = createServer((req, res) => {
    seen.push({ method: req.method, path: req.url, headers: req.headers });
    req.resume();
    req.on("end", () => {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(req.url.startsWith("/api/plan") ? { job: "stand-in" } : req.url.startsWith("/api/creatives") ? [] : { ok: true }));
    });
  });
  await new Promise((ok) => fake.listen(8799, "127.0.0.1", ok));
  const env = { ...process.env, ENGINE_URL: "http://127.0.0.1:8799", ENGINE_TOKEN: "qa-relay-token", STUDIO_PASSCODE: "", PORT: "3106" };
  const next = spawn("node_modules/.bin/next", ["start", "-p", "3106"], { env, stdio: "ignore" });
  const R = "http://localhost:3106/api/engine/relay";
  try {
    for (let i = 0; i < 60; i++) {
      if (await fetch("http://localhost:3106/api/session").then((r) => r.ok, () => false)) break;
      await new Promise((ok) => setTimeout(ok, 500));
    }
    const keyH = { "X-CBJ-Gemini-Key": "test-gemini-key", "X-CBJ-Anthropic-Key": "test-anthropic-key", "X-CBJ-Planner": "anthropic" };
    await fetch(`${R}/api/plan`, { method: "POST", headers: { ...keyH, "Content-Type": "application/json" }, body: JSON.stringify({ prompt: "qa" }) });
    await fetch(`${R}/api/meta`, { headers: keyH });
    await fetch(`${R}/api/creatives`, { headers: keyH });
    await fetch(`${R}/api/jobs/stand-in?since=0`, { headers: keyH });
    await fetch(`${R}/studio/x/v1/brief.json`, { headers: keyH });
    const at = (m, p) => seen.find((s) => s.method === m && s.path.startsWith(p));
    const carries = (s) => s && s.headers["x-cbj-gemini-key"] === "test-gemini-key" && s.headers["x-cbj-anthropic-key"] === "test-anthropic-key" && s.headers["x-cbj-planner"] === "anthropic";
    const bare = (s) => s && H.every((h) => !s.headers[h]);
    check(carries(at("POST", "/api/plan")) && at("POST", "/api/plan").headers.authorization === "Bearer qa-relay-token", "relay: POST api/plan forwards the three headers (and the relay's own token)");
    check(carries(at("GET", "/api/meta")), "relay: GET api/meta forwards the three headers");
    check(bare(at("GET", "/api/creatives")), "relay: GET api/creatives forwards none");
    check(bare(at("GET", "/api/jobs/")), "relay: GET api/jobs forwards none");
    check(bare(at("GET", "/studio/")), "relay: GET studio files forward none");
    const n = seen.length;
    const notRelayed = await fetch(`${R}/api/sprite/x`, { method: "POST", headers: keyH });
    check(notRelayed.status === 404 && seen.length === n, "relay: the POST allow list stays (api/sprite is not relayed)");
  } finally {
    next.kill("SIGTERM");
    fake.close();
  }
  // the passcode check stays: a passcode set, no cookie → 401 before the engine
  {
    const fake2 = [];
    const srv = createServer((req, res) => {
      fake2.push(req.url);
      res.end("{}");
    });
    await new Promise((ok) => srv.listen(8799, "127.0.0.1", ok));
    const env = { ...process.env, ENGINE_URL: "http://127.0.0.1:8799", ENGINE_TOKEN: "qa-relay-token", STUDIO_PASSCODE: "qa-passcode", PORT: "3106" };
    const next = spawn("node_modules/.bin/next", ["start", "-p", "3106"], { env, stdio: "ignore" });
    try {
      for (let i = 0; i < 60; i++) {
        if (await fetch("http://localhost:3106/api/session").then((r) => r.ok, () => false)) break;
        await new Promise((ok) => setTimeout(ok, 500));
      }
      const r = await fetch(`${R}/api/plan`, { method: "POST", headers: { "X-CBJ-Anthropic-Key": "test-anthropic-key", "Content-Type": "application/json" }, body: "{}" });
      check(r.status === 401 && fake2.length === 0, "relay: with a passcode and no session, a POST with keys is refused (401) before the engine");
    } finally {
      next.kill("SIGTERM");
      srv.close();
    }
  }
}
