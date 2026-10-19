// SPEC-FEEDBACK-INLINE §6, run from qa.mjs (it passes the browser and its check()); `--inline-only` runs just these.
// Online: the inline panel on Create's finished creative (a finished make picked up after a reload: the job answered in
// the browser, GETs only) and in the Edit workspace (1019-113515… v4, an edit with a proof; 1019-125939… v3): "Something
// is off", the step chips, the rows' flags (a failed check, a control row, an edit-report row) pre-filling the step and
// the item, ONE real POST /api/feedback (designer "qa-inline") with --real-feedback, else every POST is answered here;
// the designer's Edit workspace (one "What changed" card; Details hides and shows the rest and is remembered after a
// reload); Download report (GET /api/report/… answered here: the request's format and version, the file's name); the
// owner's page: a record shows its step and item, opens with its evidence, and Analyze (POST answered from
// scripts/fixtures/analysis.json: a real one is a model call). Offline: the panel says "Needs the engine", no flags.
// 1440 and 390, no horizontal overflow, no page or console errors; screenshots to qa/inline-*.
import { readFileSync } from "node:fs";
import { engineJson } from "./qa-engine.mjs";

const EDIT_CID = "1019-113515-use-same-game-design-same"; // 4 versions; v4 is an edit with a proof
const EDIT2_CID = "1019-125939-the-board-exactly-as-shown"; // 3 versions; v1 has a failed check and a review
const DESIGNER = "qa-inline";
const STEP_PROOF = "the edit report (what changed, what was kept)";
const HONEST = "Read by the person who tunes the engine. Nothing changes automatically.";
const analysisFixture = JSON.parse(readFileSync(new URL("./fixtures/analysis.json", import.meta.url), "utf8"));

export default async function inlineChecks({ browser, base, label, check, featurePage, VIEWPORTS, CID, realFeedback }) {
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const shot = async (page, file, full = true) => {
    await page.waitForTimeout(400);
    await page.screenshot({ path: `qa/${file}`, fullPage: full, scale: "css" });
  };
  const elShot = async (page, loc, file) => {
    await page.waitForTimeout(400);
    const unstick = await page.addStyleTag({ content: "header { position: static !important; }" });
    await loc.screenshot({ path: `qa/${file}`, scale: "css" });
    await unstick.evaluate((el) => el.remove());
  };
  const panel = (page) => page.getByRole("region", { name: "Was this what you asked?" });
  const flags = (page) => page.locator('button[aria-label^="Feedback about "]:not([aria-label="Feedback about the studio"])');
  const flag = (page, title) => page.getByRole("button", { name: `Feedback about ${title}`, exact: true });
  const pressed = async (loc) => (await loc.getAttribute("aria-pressed")) === "true";
  const inView = async (page, loc) => {
    // the smooth scroll: up to ~2 s over a long phone page
    const h = page.viewportSize().height;
    for (const t0 = Date.now(); Date.now() - t0 < 5000; await page.waitForTimeout(200)) {
      const b = await loc.boundingBox();
      if (b && b.y >= -1 && b.y < h * 0.6) return true;
    }
    return false;
  };
  // a version without a viewer review answers 404 for its review.json (the review line asks for it): allowed, one per response
  const guard = (page) => {
    const log = { review404: 0 };
    page.on("response", (r) => {
      if (r.status() === 404 && /\/review\.json$/.test(new URL(r.url()).pathname)) log.review404++;
    });
    return log;
  };
  const noErrors = (errors, what, log) => {
    const r404 = errors.filter((e) => /status of 404/.test(e));
    const bad = errors.filter((e) => !/status of 404/.test(e)).concat(r404.slice(log ? log.review404 : 0));
    check(bad.length === 0, `${what}: no page/console errors${log?.review404 ? ` (besides ${log.review404} review.json 404)` : ""} ${bad.join("; ")}`);
  };

  // ── offline ─────────────────────────────────────────────────────────────────────────────────────
  if (label === "offline") {
    for (const [vpName, vp] of VIEWPORTS) {
      const { ctx, page, errors } = await featurePage(vp);
      const log = guard(page);
      for (const [name, path, marker] of [
        ["showcase", `/showcase/${CID}`, "What v17 changed"],
        ["edit", `/edit?c=${CID}&v=13`, "What changed"],
      ]) {
        const tag = `offline ${vpName} ${name}:`;
        await page.goto(base + path, { waitUntil: "load" });
        await page.getByText(marker).first().waitFor({ timeout: 15000 });
        await page.waitForTimeout(800);
        const p = panel(page);
        check((await p.count()) === 1 && (await p.getByText("Needs the engine").count()) === 1, `${tag} the panel says "Needs the engine"`);
        check((await p.getByRole("button").count()) === 0 && (await p.locator("input, textarea").count()) === 0, `${tag} nothing clickable in the panel`);
        check((await flags(page).count()) === 0, `${tag} no flag buttons`);
        check((await page.getByRole("group", { name: "Download report" }).count()) === 0, `${tag} no Download report`);
        check((await overflow(page)) === 0, `${tag} no horizontal overflow`);
        await shot(page, `inline-offline-${name}-${vpName}.png`);
      }
      noErrors(errors, `offline ${vpName} inline`, log);
      await ctx.close();
    }
    return;
  }

  // ── online ──────────────────────────────────────────────────────────────────────────────────────
  const [editVersions, edit2Versions] = await Promise.all([engineJson(`/api/creatives/${EDIT_CID}`), engineJson(`/api/creatives/${EDIT2_CID}`)]);
  const readyVersion = edit2Versions[0]; // a make on the Create page is a new creative: v1
  const v4 = editVersions.find((x) => x.n === 4);
  const failedCheck = (readyVersion.checks || []).find((c) => c.status === "failed" || c.status === "fail")?.check;
  let realPosts = 0;
  let realId = "";

  /** Every feedback POST is answered here (and kept), except the one real qa-inline record. */
  const answerFeedback = async (page, bodies, allowReal) => {
    await page.route("**/api/feedback", async (r) => {
      if (r.request().method() !== "POST") return r.continue();
      const b = r.request().postDataJSON();
      bodies.push(b);
      if (allowReal && realFeedback && realPosts === 0) {
        realPosts++;
        const resp = await r.fetch();
        const j = await resp.json();
        realId = j.id || "";
        return r.fulfill({ response: resp, json: j });
      }
      return r.fulfill({
        json: { id: "fb-qa-intercepted", created: "2026-10-19 15:00:00", designer: b.designer || "anonymous", page: b.page, area: b.area, kind: b.kind, wrong: b.wrong, expected: b.expected || "", rating: b.rating ?? null, step: b.step ?? "result", item: b.item ?? null, scene: {} },
      });
    });
  };
  /** GET /api/report/… answered here: the format and the version it asked for. */
  const answerReports = async (page, asked) => {
    await page.route("**/api/report/**", (r) => {
      const u = new URL(r.request().url());
      asked.push({ path: u.pathname, format: u.searchParams.get("format"), version: u.searchParams.get("version") });
      const html = u.searchParams.get("format") === "html";
      return r.fulfill({ status: 200, contentType: html ? "text/html" : "text/markdown", body: html ? "<!doctype html><title>qa report</title><h1>qa report</h1>" : "# qa report\n" });
    });
  };

  for (const [vpName, vp] of VIEWPORTS) {
    // ── 1. Create, phase ready ────────────────────────────────────────────────────────────────────
    {
      const tag = `${vpName} inline create:`;
      const { ctx, page, errors, posts } = await featurePage(vp);
      const log = guard(page);
      const bodies = [];
      await answerFeedback(page, bodies, false);
      await page.addInitScript((j) => localStorage.setItem("cbjStudioJob", JSON.stringify(j)), { id: "qa-ready", kind: "make", page: "create" });
      await page.route("**/api/jobs", (r) => r.fulfill({ json: [{ id: "qa-ready", status: "done" }] }));
      await page.route("**/api/jobs/qa-ready*", (r) =>
        r.fulfill({ json: { id: "qa-ready", kind: "make", status: "done", stage: "done", lines: [], n_lines: 0, result: readyVersion, elapsed: 1 } }),
      );
      const reports = [];
      await answerReports(page, reports);
      await page.goto(base + "/", { waitUntil: "load" });
      const p = panel(page);
      const shown = await p.waitFor({ timeout: 15000 }).then(() => true, () => false);
      check(shown, `${tag} the panel under the finished creative`);
      const creative = page.getByRole("region", { name: "Creative", exact: true });
      const [cb, pb] = [await creative.boundingBox(), await p.boundingBox()];
      check(Boolean(cb && pb) && pb.y >= cb.y + cb.height - 1, `${tag} the panel is below the player`);
      check((await p.getByRole("heading", { name: "Was this what you asked?" }).count()) === 1 && (await p.getByText(HONEST).count()) === 1, `${tag} title and the honesty line`);
      const [yes, off] = [p.getByRole("button", { name: "Yes, as asked" }), p.getByRole("button", { name: "Something is off" })];
      check((await yes.count()) === 1 && (await off.count()) === 1 && (await p.getByRole("button", { name: "Something is missing" }).count()) === 1 && (await p.getByRole("button", { name: "I have an idea" }).count()) === 1, `${tag} two large choices and two quiet ones`);
      check((await p.locator("form").count()) === 0, `${tag} closed until a choice`);
      // Download report next to "Edit this creative" (the header row) and "Give feedback" still there
      const report = page.getByRole("group", { name: "Download report" });
      const editLink = page.getByRole("link", { name: "Edit this creative" }).first();
      const [rb, eb] = [await report.boundingBox(), await editLink.boundingBox()];
      check((await report.count()) === 1 && rb && eb && Math.abs(rb.y + rb.height / 2 - (eb.y + eb.height / 2)) < (vpName === "390" ? 60 : 4), `${tag} Download report next to Edit this creative`);
      check((await page.getByRole("button", { name: "Give feedback" }).count()) === 1, `${tag} the Give feedback dialog button is unchanged`);
      await shot(page, `inline-create-${vpName}.png`);

      // a failed check's flag → step from the check's prefix, the item = the check's name
      if (failedCheck) {
        const f = flag(page, failedCheck);
        check((await f.count()) === 1, `${tag} a flag on the failed check "${failedCheck}"`);
        await f.click();
        check(await inView(page, p), `${tag} the flag scrolls the panel into view`);
        const wantStep = /^Rules:/.test(failedCheck) ? "the gameplay (the moves and the clock)" : /^(Video|Image|Reference):/.test(failedCheck) ? "how the request was read" : "the whole result";
        check(
          (await pressed(off)) && (await pressed(p.getByRole("button", { name: wantStep, exact: true }))) && (await p.getByLabel(/Which thing\?/).inputValue()) === failedCheck,
          `${tag} the check's flag opens "Something is off", step "${wantStep}", item "${failedCheck}"`,
        );
        check((await page.evaluate(() => document.activeElement?.tagName)) === "TEXTAREA", `${tag} the cursor is in "What happened?"`);
      }
      const passChecks = (readyVersion.checks || []).filter((c) => c.status === "pass").map((c) => c.check);
      check((await flags(page).count()) >= 1, `${tag} flags on the rows (${await flags(page).count()})`);
      const passFlag = passChecks.length ? await flag(page, passChecks[0]).count() : 0;
      check(passFlag === 0, `${tag} no flag on a passed check`);
      // the step chips: no edit report for a first version
      const chipTexts = await p.locator("fieldset").filter({ hasText: "Which step is it about?" }).getByRole("button").allInnerTexts();
      check(chipTexts.length === 8 && !chipTexts.includes(STEP_PROOF) && chipTexts[0] === "the whole result", `${tag} 8 step chips, result first, no edit report on a v1 (${chipTexts.length})`);
      // a control row's flag → plan, the control's title; the area follows the step
      const ctlTitle = (await page.getByRole("region", { name: "What the tool understood" }).locator("tbody th").first().innerText()).split("\n")[0].trim();
      await flag(page, ctlTitle).click();
      check(
        (await pressed(p.getByRole("button", { name: "how the request was read", exact: true }))) &&
          (await p.getByLabel(/Which thing\?/).inputValue()) === ctlTitle &&
          (await p.getByText(/^about: how the prompt was understood/).count()) === 1,
        `${tag} a control row's flag: step "how the request was read", item "${ctlTitle}", about: how the prompt was understood`,
      );
      // a review line ("not as asked"), when the review has one
      const notAsked = (readyVersion.review?.match || []).find((m) => m.verdict === "no" || m.verdict === "partial");
      if (notAsked) {
        await flag(page, notAsked.control).first().click();
        check((await pressed(p.getByRole("button", { name: "the viewer's review", exact: true }))) && (await p.getByLabel(/Which thing\?/).inputValue()) === notAsked.control, `${tag} a review line's flag: step "the viewer's review", item "${notAsked.control}"`);
      }
      // change the area by hand, then send (answered here) and read the body
      await p.getByRole("button", { name: "change", exact: true }).click();
      await p.getByRole("button", { name: "the level or the board", exact: true }).click();
      await p.getByLabel("What happened?").fill("qa: the request was read as a copy of the board.");
      await p.getByLabel("Your name").fill(DESIGNER);
      await elShot(page, p, `inline-create-panel-${vpName}.png`);
      await p.getByRole("button", { name: "Send", exact: true }).click();
      const thanks = p.getByText(/^Thanks, saved as fb-/);
      await thanks.waitFor({ timeout: 10000 });
      const b = bodies.at(-1) || {};
      const step = notAsked ? "review" : "plan";
      check(
        b.page === "create" && b.creative_id === EDIT2_CID && b.version === readyVersion.n && b.kind === "wrong" && b.step === step && b.area === "level" && b.designer === DESIGNER && Boolean(b.item),
        `${tag} the POST (answered here): ${JSON.stringify(b)}`,
      );
      check(/it is tied to /.test(await thanks.innerText()), `${tag} thanks line: "${(await thanks.innerText()).replace(/\s+/g, " ")}"`);
      check((await overflow(page)) === 0, `${tag} no horizontal overflow`);
      check(!posts.some((x) => /\/api\/(plan|make|direct|review|upload|preview|enhance|trends|lessons)$/.test(x)), `${tag} no workflow POSTs`);
      noErrors(errors, tag.slice(0, -1), log);
      await ctx.close();
    }

    // ── 2. Edit workspace, a designer's view ─────────────────────────────────────────────────────
    {
      const tag = `${vpName} inline edit:`;
      const { ctx, page, errors, posts } = await featurePage(vp);
      const log = guard(page);
      const bodies = [];
      const reports = [];
      await answerFeedback(page, bodies, vpName === "1440");
      await answerReports(page, reports);
      await page.goto(`${base}/edit?c=${EDIT_CID}&v=4`, { waitUntil: "load" });
      await page.getByText("What changed").first().waitFor({ timeout: 15000 });
      const p = panel(page);
      await p.getByRole("button", { name: "Something is off" }).waitFor({ timeout: 15000 });
      const card = page.getByRole("region", { name: "What changed" });
      const sw = page.getByRole("switch", { name: "Details" });
      const detailsBtn = card.getByRole("button", { name: "Details", exact: true });
      await page.waitForTimeout(800);

      // the default view: one card, the contract, no rows; the cut parts are gone
      check((await page.getByRole("button", { name: "Give feedback" }).count()) === 0 && (await page.getByText(/Something off in v\d/).count()) === 0, `${tag} the panel replaced the old line and button`);
      check((await sw.getAttribute("aria-checked")) === "false" && (await detailsBtn.getAttribute("aria-pressed")) === "false", `${tag} Details off by default`);
      check((await card.getByText("Locked", { exact: true }).count()) === 1 && (await card.getByText("Allowed", { exact: true }).count()) === 1 && (await card.getByText("Forbidden", { exact: true }).count()) === 1, `${tag} What changed: Locked / Allowed / Forbidden`);
      check(v4.proof?.verdict ? (await card.getByText(v4.proof.verdict).count()) === 1 : true, `${tag} What changed: the verdict line`);
      check((await card.getByText(/^As a viewer: |Not reviewed as a viewer yet\./).count()) === 1, `${tag} What changed: the viewer's line`);
      check((await card.getByRole("group", { name: "Download report" }).count()) === 1, `${tag} What changed: Download report`);
      const hidden = ["Compare", "Metadata", "Level and gameplay", "Versions", "Change summary", "As a viewer"];
      const present = [];
      for (const n of hidden) if ((await page.getByRole("region", { name: n, exact: true }).count()) > 0) present.push(n);
      check(present.length === 0, `${tag} hidden by default: ${hidden.join(", ")}${present.length ? " SHOWN " + present.join(", ") : ""}`);
      check((await flags(page).count()) === 0 && (await card.getByText("Checklist").count()) === 0, `${tag} no rows, no checklist, no flags`);
      check((await page.getByText("Preserved by default").count()) === 0 && (await page.getByText("Everything you do not mention stays as it is; the report proves it.").count()) === 1, `${tag} the preserved list is one line`);
      const examples = page.getByText("Try an edit:").locator("xpath=..").getByRole("button");
      check((await examples.count()) === 4 && /more$/.test(await examples.last().innerText()), `${tag} three edit examples and "more"`);
      const music = page.locator("summary", { hasText: "More: music" });
      check((await music.count()) === 1 && (await page.getByRole("region", { name: "Soundtrack", exact: true }).isVisible().catch(() => false)) === false, `${tag} the soundtrack folded under "More: music"`);
      check((await overflow(page)) === 0, `${tag} default: no horizontal overflow`);
      await shot(page, `inline-edit-default-${vpName}.png`);

      // Download report: HTML by default, Markdown beside it; the engine's file names
      for (const [btn, fmt] of [[card.getByRole("button", { name: "Download report HTML", exact: true }), "html"], [card.getByRole("button", { name: "Download report as Markdown" }), "md"]]) {
        const dl = page.waitForEvent("download");
        await btn.click();
        const file = await dl;
        const asked = reports.at(-1) || {};
        check(
          file.suggestedFilename() === `${EDIT_CID}-v4-report.${fmt}` && asked.format === fmt && asked.version === "4" && asked.path.endsWith(`/api/report/${EDIT_CID}`),
          `${tag} Download report ${fmt}: ${asked.path}?format=${asked.format}&version=${asked.version} → ${file.suggestedFilename()}`,
        );
      }

      // the panel: "Something is off" → the step chips with the edit report (an edit), default the whole result
      await p.getByRole("button", { name: "Something is off" }).click();
      const chips = await p.locator("fieldset").filter({ hasText: "Which step is it about?" }).getByRole("button").allInnerTexts();
      check(chips.length === 9 && chips.includes(STEP_PROOF) && (await pressed(p.getByRole("button", { name: "the whole result", exact: true }))), `${tag} 9 step chips with the edit report; "the whole result" by default`);
      check((await p.getByText(/^about: something else/).count()) === 1 && (await p.getByRole("button", { name: /of 5$/ }).count()) === 5, `${tag} about: something else; the 1-5 rating`);
      await p.getByRole("button", { name: "Yes, as asked" }).click();
      check((await p.getByText("What did you like?").count()) === 1 && (await p.getByText("What did you expect instead?").count()) === 0 && (await p.getByRole("button", { name: /of 5$/ }).count()) === 0, `${tag} "Yes, as asked": no expected, no rating`);
      await p.getByRole("button", { name: "Something is off" }).click();
      await elShot(page, p, `inline-edit-panel-open-${vpName}.png`);

      // Details on (the card's button): the rest comes back where it was
      await detailsBtn.click();
      await page.waitForTimeout(600);
      const back = [];
      for (const n of ["Compare", "Metadata", "Level and gameplay", "As a viewer", "What the tool understood"]) if ((await page.getByRole("region", { name: n, exact: true }).count()) === 1) back.push(n);
      check((await sw.getAttribute("aria-checked")) === "true" && back.length === 5, `${tag} Details on: ${back.join(", ")} shown`);
      check((await card.getByText("Checklist").count()) === 1 && (await flag(page, "Captions").count()) === 1, `${tag} Details on: the full report with its rows and their flags`);
      await page.reload({ waitUntil: "load" });
      await page.getByText("What changed").first().waitFor({ timeout: 15000 });
      await page.getByRole("region", { name: "Compare", exact: true }).waitFor({ timeout: 10000 }).catch(() => null);
      check((await sw.getAttribute("aria-checked")) === "true" && (await page.getByRole("region", { name: "Compare", exact: true }).count()) === 1 && (await page.evaluate(() => localStorage.getItem("cbj.edit.details"))) === "1", `${tag} Details remembered after a reload`);
      await p.getByRole("button", { name: "Something is off" }).waitFor({ timeout: 15000 });
      await page.waitForTimeout(600);
      check((await overflow(page)) === 0, `${tag} details: no horizontal overflow`);
      await shot(page, `inline-edit-details-${vpName}.png`);

      // an edit-report row's flag → step: the edit report, item: the row's title
      const row = (v4.proof?.rows || []).find((r) => r.status === "asked")?.title || "Captions";
      await flag(page, row).click();
      check(await inView(page, p), `${tag} the row's flag scrolls the panel into view`);
      check(
        (await pressed(p.getByRole("button", { name: "Something is off" }))) && (await pressed(p.getByRole("button", { name: STEP_PROOF, exact: true }))) && (await p.getByLabel(/Which thing\?/).inputValue()) === row,
        `${tag} the row's flag pre-fills step "${STEP_PROOF}" and item "${row}"`,
      );
      check((await p.getByText(/^about: an edit that changed too much or too little/).count()) === 1, `${tag} about: the edit (from the step)`);
      await p.getByLabel("What happened?").fill(`qa run (inline panel): checking that a note is tied to the edit report row "${row}".`);
      await p.getByLabel(/What did you expect instead/).fill("Nothing: this is a qa record.");
      await p.getByLabel("Your name").fill(DESIGNER);
      await p.getByRole("button", { name: "2 of 5" }).click();
      await elShot(page, p, `inline-edit-panel-flag-${vpName}.png`);
      await p.getByRole("button", { name: "Send", exact: true }).click();
      const thanks = p.getByText(/^Thanks, saved as fb-/);
      await thanks.waitFor({ timeout: 15000 });
      const t = (await thanks.innerText()).replace(/\s+/g, " ");
      check(t.includes(`it is tied to ${STEP_PROOF}, ${row}`), `${tag} thanks line: "${t}"`);
      const b = bodies.at(-1) || {};
      check(
        b.page === "edit" && b.creative_id === EDIT_CID && b.version === 4 && b.kind === "wrong" && b.step === "proof" && b.item === row && b.area === "edit" && b.rating === 2 && b.designer === DESIGNER && !("process" in b),
        `${tag} the POST${vpName === "1440" && realFeedback ? " (real)" : " (answered here)"}: ${JSON.stringify(b)}`,
      );
      await elShot(page, p, `inline-edit-thanks-${vpName}.png`);
      await p.getByRole("button", { name: "Send another" }).click();
      check((await p.locator("form").count()) === 0 && !(await pressed(p.getByRole("button", { name: "Something is off" }))), `${tag} Send another: the panel starts again`);

      // Details off (the header switch), remembered too; another version starts the panel afresh
      await sw.click();
      await page.waitForTimeout(400);
      check((await page.getByRole("region", { name: "Compare", exact: true }).count()) === 0 && (await flags(page).count()) === 0, `${tag} the header switch hides the details again`);
      await page.reload({ waitUntil: "load" });
      await page.getByText("What changed").first().waitFor({ timeout: 15000 });
      await page.waitForTimeout(800);
      check((await sw.getAttribute("aria-checked")) === "false" && (await page.getByRole("region", { name: "Compare", exact: true }).count()) === 0, `${tag} Details off remembered`);
      await p.getByRole("button", { name: "Something is off" }).click();
      await page.getByRole("tab", { name: /^v2/ }).click();
      await page.waitForTimeout(500);
      check((await p.locator("form").count()) === 0, `${tag} another version shown: the panel starts afresh`);
      check(!posts.some((x) => /\/api\/(plan|make|direct|review|upload|preview|enhance|trends|lessons)$/.test(x)), `${tag} no workflow POSTs`);
      noErrors(errors, tag.slice(0, -1), log);
      await ctx.close();
    }

    // ── 3. Edit workspace, the other creative (v3): the card, the panel, the Markdown report ─────
    {
      const tag = `${vpName} inline edit v3:`;
      const { ctx, page, errors } = await featurePage(vp);
      const log = guard(page);
      const reports = [];
      await answerReports(page, reports);
      await page.goto(`${base}/edit?c=${EDIT2_CID}&v=3`, { waitUntil: "load" });
      await page.getByText("What changed").first().waitFor({ timeout: 15000 });
      const p = panel(page);
      await p.getByRole("button", { name: "Something is off" }).waitFor({ timeout: 15000 });
      const card = page.getByRole("region", { name: "What changed" });
      check((await card.getByText(/What v3 changed from v\d/).count()) === 1, `${tag} What changed from the version before`);
      const dl = page.waitForEvent("download");
      await card.getByRole("button", { name: "Download report as Markdown" }).click();
      const file = await dl;
      check(file.suggestedFilename() === `${EDIT2_CID}-v3-report.md` && reports.at(-1)?.format === "md" && reports.at(-1)?.version === "3", `${tag} Markdown report: ${file.suggestedFilename()}`);
      check((await overflow(page)) === 0, `${tag} no horizontal overflow`);
      await shot(page, `inline-edit-v3-${vpName}.png`);
      noErrors(errors, tag.slice(0, -1), log);
      await ctx.close();
    }

    // ── 4. The owner's page: a record's step, item, evidence and analysis ──────────────────────
    {
      const tag = `${vpName} inline owner:`;
      const { ctx, page, errors, posts } = await featurePage(vp);
      const analyzed = [];
      const FIX_ID = "fb-qa-inline-fixture";
      const listing = await engineJson("/api/feedback?limit=50");
      const mine = listing.records.find((r) => r.designer === DESIGNER && r.step === "proof" && r.item);
      const id = mine?.id || FIX_ID;
      if (!mine) {
        // no qa-inline record on this engine (a run without --real-feedback): the list and the record answered here
        const rec = { id: FIX_ID, created: "2026-10-19 15:10:00", designer: DESIGNER, page: "edit", area: "edit", kind: "wrong", wrong: "qa: a fixture record", expected: "", rating: 2, step: "proof", item: "Other assets", scene: { creative_id: EDIT_CID, version: 4, workflow: "edit", prompt: v4.prompt } };
        await page.route("**/api/feedback?*", (r) => r.fulfill({ json: { count: 1, total: 1, records: [rec], designers: [DESIGNER], areas: ["edit"], kinds: ["wrong"], creatives: [EDIT_CID] } }));
        await page.route(`**/api/feedback/${FIX_ID}`, (r) =>
          r.fulfill({ json: { ...rec, evidence: { step: "proof", words: STEP_PROOF, item: "Other assets", facts: { proof: v4.proof && { verdict: v4.proof.verdict, ok: v4.proof.ok } }, lines: [{ stage: "proof", text: v4.proof?.verdict || "the report" }] }, analysis: null } }),
        );
      }
      await page.route("**/api/feedback/*/analyze", async (r) => {
        analyzed.push(new URL(r.request().url()).pathname);
        await new Promise((ok) => setTimeout(ok, 700)); // long enough to see the waiting line
        return r.fulfill({ json: { ...analysisFixture, record: id } });
      });
      await page.goto(base + "/feedback", { waitUntil: "load" });
      const list = page.getByRole("list", { name: "Feedback records, newest first" });
      await list.waitFor({ timeout: 15000 });
      const row = list.locator(":scope > li").filter({ hasText: id }).first();
      await row.waitFor({ timeout: 10000 });
      check((await row.getByText(STEP_PROOF, { exact: true }).count()) === 1, `${tag} the record's step chip (${mine ? "the real record" : "a fixture record"} ${id})`);
      const item = mine?.item || "Other assets";
      check((await row.locator(".font-mono", { hasText: item }).count()) >= 1, `${tag} the item in monospace: ${item}`);
      await row.getByRole("button", { name: "What the engine did" }).click();
      const ev = row.locator(`[id="ev-${id}"]`);
      await ev.locator("dl, p").first().waitFor({ timeout: 15000 });
      const dts = await ev.locator("dt").allInnerTexts();
      check(dts.length >= 1 && (await ev.getByText(`The engine at this step: ${STEP_PROOF}`).count()) === 1, `${tag} evidence: facts ${dts.join(", ")}`);
      check((await ev.getByRole("list", { name: "The engine's lines of this stage" }).locator("li").count()) >= 0, `${tag} evidence: the engine's lines`);
      const analyze = ev.getByRole("button", { name: /^(Analyze what happened|Analyze again)$/ });
      await analyze.click();
      await page.waitForTimeout(200);
      check((await ev.getByText("Reading the evidence…", { exact: false }).count()) === 1 && (await analyze.isDisabled()), `${tag} analysing: the waiting line, the button disabled`);
      const card = ev.getByRole("region", { name: "Analysis" });
      await card.waitFor({ timeout: 10000 });
      check(analyzed.length === 1 && analyzed[0].endsWith(`/api/feedback/${id}/analyze`), `${tag} Analyze posts ${analyzed[0]} (answered here)`);
      check(
        (await card.getByText("taste", { exact: true }).count()) === 1 &&
          (await card.getByText("strong", { exact: true }).count()) === 1 &&
          (await card.getByRole("heading", { name: "What happened" }).count()) === 1 &&
          (await card.getByRole("heading", { name: "Why" }).count()) === 1 &&
          (await card.getByRole("heading", { name: "Smallest change" }).count()) === 1 &&
          (await card.locator("blockquote").count()) === analysisFixture.evidence.length &&
          (await card.getByText("not in the evidence").count()) === 1,
        `${tag} the analysis card: verdict, confidence, what happened, why, ${analysisFixture.evidence.length} quotes, smallest change, not in the evidence`,
      );
      check((await ev.getByRole("button", { name: "Analyze again" }).count()) === 1, `${tag} the button now says "Analyze again"`);
      check((await overflow(page)) === 0, `${tag} no horizontal overflow`);
      await shot(page, `inline-owner-${vpName}.png`);
      check(!posts.some((x) => /\/api\/(plan|make|direct|review|upload|preview|enhance|trends|lessons)$/.test(x)), `${tag} no workflow POSTs`);
      noErrors(errors, tag.slice(0, -1));
      await ctx.close();
    }
  }
  check(!realFeedback || (realPosts === 1 && realId.startsWith("fb-")), `inline: real /api/feedback POSTs: ${realPosts}${realId ? ` (${realId})` : ""}`);
}
