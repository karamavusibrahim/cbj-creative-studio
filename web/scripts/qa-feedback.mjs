// SPEC-FEEDBACK §5, run from qa.mjs (it passes the browser and its check()). Online: the Give feedback entry points
// (the header and Create; Edit and the showcase carry the inline panel since SPEC-FEEDBACK-INLINE, checked in
// qa-feedback-inline.mjs), the dialog (focus, Esc, the remembered name), ONE real POST /api/feedback with --real-feedback (else
// intercepted), the /feedback Records tab from the live engine (filters, Download .md), the Lessons tab from
// scripts/fixtures/lessons.json by interception (every POST /api/lessons is answered here: a distil is a model call).
// Offline: no enabled feedback button, /feedback says "Needs the engine". Locked (/api/session intercepted): the owner
// card on /feedback, and Give feedback opens the unlock dialog first.
import { readFileSync } from "node:fs";
import { engineJson } from "./qa-engine.mjs";

const fixture = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8"));
const QA_RECORD = { page: "general", area: "website", kind: "idea", designer: "qa", wrong: "qa run: a test idea" };
const READY_CID = "1018-110841-an-easy-color-block-jam"; // a creative the test records point at
const NAME_KEY = "cbj.designer";

export default async function feedbackChecks({ browser, base, label, check, featurePage, VIEWPORTS, CID, realFeedback }) {
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const shot = async (page, file) => {
    await page.waitForTimeout(350);
    await page.screenshot({ path: `qa/${file}`, fullPage: true, scale: "css" });
  };
  const enabledSoon = async (loc, ms = 10000) => {
    for (const t0 = Date.now(); Date.now() - t0 < ms; ) {
      if ((await loc.count()) === 1 && (await loc.isEnabled())) return true;
      await new Promise((ok) => setTimeout(ok, 200));
    }
    return false;
  };
  const fbButtons = (page) => page.getByRole("button", { name: /^(Give feedback|Feedback about the studio)$/ });
  const noErrors = (errors, what, allow = /$^/) => {
    const bad = errors.filter((e) => !allow.test(e));
    check(bad.length === 0, `${what}: no page/console errors ${bad.join("; ")}`);
  };

  // ── offline ─────────────────────────────────────────────────────────────────────────────────────
  if (label === "offline") {
    const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
    for (const [path, marker] of [
      ["/", "Engine offline"],
      [`/showcase/${CID}`, "What v17 changed"],
      [`/edit?c=${CID}&v=13`, "What changed"],
    ]) {
      await page.goto(base + path, { waitUntil: "load" });
      await page.getByText(marker).first().waitFor({ timeout: 15000 });
      await page.waitForTimeout(500);
      const all = await fbButtons(page).all();
      const enabled = (await Promise.all(all.map((b) => b.isEnabled()))).filter(Boolean).length;
      const tips = await page.locator('span[title="Needs the engine"]').filter({ has: fbButtons(page) }).count();
      check(all.length >= 1 && enabled === 0 && tips === all.length, `offline ${path}: ${all.length} feedback button(s), none enabled, each "Needs the engine"`);
    }
    for (const [vpName, vp] of VIEWPORTS) {
      const p2 = await (await browser.newContext({ viewport: vp })).newPage();
      await p2.goto(base + "/feedback", { waitUntil: "load" });
      const ok = await p2.getByRole("heading", { name: "Needs the engine" }).waitFor({ timeout: 15000 }).then(() => true, () => false);
      check(ok && (await p2.getByRole("tab").count()) === 0, `offline ${vpName} /feedback: "Needs the engine", no tabs`);
      check((await overflow(p2)) === 0, `offline ${vpName} /feedback: no horizontal overflow`);
      await shot(p2, `offline-feedback-${vpName}.png`);
      await p2.context().close();
    }
    noErrors(errors, "offline feedback");
    await ctx.close();
    return;
  }

  // ── locked ──────────────────────────────────────────────────────────────────────────────────────
  if (label === "locked") {
    const { ctx, page, errors, posts } = await featurePage({ width: 1440, height: 900 });
    await page.route("**/api/session", (r) => (r.request().method() === "GET" ? r.fulfill({ json: { unlocked: false, required: true } }) : r.abort()));
    await page.goto(base + "/feedback", { waitUntil: "load" });
    const owner = await page.getByRole("heading", { name: "This page is for the studio's owner." }).waitFor({ timeout: 15000 }).then(() => true, () => false);
    check(owner && (await page.getByRole("tab").count()) === 0, "locked /feedback: the owner card, no tabs");
    await shot(page, "locked-feedback-1440.png");
    await page.setViewportSize({ width: 390, height: 844 });
    check((await overflow(page)) === 0, "locked 390 /feedback: no horizontal overflow");
    await shot(page, "locked-feedback-390.png");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByRole("main").getByRole("button", { name: "Unlock", exact: true }).click();
    check((await page.locator("dialog[open]").getByText("Unlock the studio").count()) === 1, "locked /feedback: Unlock opens the passcode dialog");
    await page.screenshot({ path: "qa/locked-feedback-unlock-1440.png", scale: "css" });
    await page.keyboard.press("Escape");
    for (const [path, marker, name] of [
      ["/", "Engine online", "Feedback about the studio"],
      [`/edit?c=${CID}&v=13`, "What changed", "Something is off"],
    ]) {
      await page.goto(base + path, { waitUntil: "load" });
      await page.getByText(marker).first().waitFor({ timeout: 15000 });
      await page.getByRole("button", { name, exact: true }).first().click();
      const dlg = page.locator("dialog[open]");
      await dlg.first().waitFor({ timeout: 5000 });
      check(
        (await dlg.getByText("Unlock the studio").count()) === 1 && (await page.getByText("Tell the studio owner").count()) === 0,
        `locked ${path}: ${name} opens the unlock dialog first`,
      );
      await page.keyboard.press("Escape");
      await page.waitForTimeout(200);
      check((await page.locator("dialog[open]").count()) === 0, `locked ${path}: cancelling the passcode opens no feedback dialog`);
    }
    check(!posts.some((p) => /\/api\/(feedback|lessons|session)$/.test(p)), "locked: nothing posted");
    noErrors(errors, "locked feedback");
    await ctx.close();
    return;
  }

  // ── online ──────────────────────────────────────────────────────────────────────────────────────
  const lessons = fixture("lessons");
  const v1 = { ...fixture("lessons-real-v1"), versions: lessons.versions, current: lessons.current, corrections: lessons.corrections };
  const readyVersions = await engineJson(`/api/creatives/${READY_CID}`);
  const readyVersion = readyVersions[0]; // a make on the Create page is a new creative: v1
  let realPosts = 0;

  for (const [vpName, vp] of VIEWPORTS) {
    const tag = `${vpName} feedback:`;
    const { ctx, page, errors, posts } = await featurePage(vp);
    const lessonPosts = [];
    let lessonsMode = "fixture";
    await page.route("**/api/lessons*", async (r) => {
      const req = r.request();
      if (req.method() === "POST") {
        const body = req.postDataJSON();
        lessonPosts.push(body);
        await new Promise((ok) => setTimeout(ok, 700)); // long enough to see the waiting line
        if (body.action === "rollback") return r.fulfill({ json: { ...v1, current: body.version } });
        if (body.action === "correct") {
          const meta = { ...lessons.meta, version: 3, generated: "2026-10-18 14:30:00", corrections: 2, previous: 2, dropped: [] };
          const corr = { id: "corr-qa", created: "2026-10-18 14:29:40", text: body.text, version_before: 2 };
          return r.fulfill({ json: { ...lessons, meta, versions: [...lessons.versions, meta], current: 3, corrections: [...lessons.corrections, corr] } });
        }
        return r.fulfill({ status: 400, json: { detail: "distill is not run in qa" } });
      }
      if (lessonsMode === "empty") return r.fulfill({ json: { empty: true, versions: [], current: null, corrections: [] } });
      return r.fulfill({ json: /version=1\b/.test(req.url()) ? v1 : lessons });
    });
    // the qa record: real once (1440, --real-feedback), else answered here
    await page.route("**/api/feedback", async (r) => {
      if (r.request().method() !== "POST") return r.continue();
      if (realFeedback && vpName === "1440" && realPosts === 0) {
        realPosts++;
        return r.continue();
      }
      const b = r.request().postDataJSON();
      return r.fulfill({ json: { id: "fb-qa-intercepted", created: "2026-10-18 14:00:00", designer: b.designer || "anonymous", page: b.page, area: b.area, kind: b.kind, wrong: b.wrong, expected: b.expected || "", rating: b.rating ?? null, scene: {} } });
    });

    // 1. the four entry points
    await page.goto(base + "/", { waitUntil: "load" });
    await page.locator('[role="status"]').filter({ hasText: "Online" }).first().waitFor({ timeout: 15000 });
    const headerBtn = page.getByRole("button", { name: "Feedback about the studio" });
    check(await enabledSoon(headerBtn), `${tag} header icon button, enabled`);
    const navLinks = await page.getByRole("navigation", { name: "Main" }).first().getByRole("link").allInnerTexts();
    check(navLinks.join(",") === "Create,Edit,Showcase,Feedback", `${tag} nav: ${navLinks.join(" · ")}`);

    // Create, phase ready: a finished make picked up after a reload (the job list and the job answered here, GETs only)
    const ready = await ctx.newPage();
    await ready.addInitScript((j) => localStorage.setItem("cbjStudioJob", JSON.stringify(j)), { id: "qa-ready", kind: "make", page: "create" });
    await ready.route("**/api/jobs", (r) => r.fulfill({ json: [{ id: "qa-ready", status: "done" }] }));
    await ready.route("**/api/jobs/qa-ready*", (r) =>
      r.fulfill({ json: { id: "qa-ready", kind: "make", status: "done", stage: "done", lines: [], n_lines: 0, result: readyVersion, elapsed: 1 } }),
    );
    await ready.goto(base + "/", { waitUntil: "load" });
    const createBtn = ready.getByRole("button", { name: "Give feedback" });
    const createOk = await createBtn.waitFor({ timeout: 15000 }).then(() => true, () => false);
    check(createOk && (await enabledSoon(createBtn)) && (await ready.getByRole("button", { name: "Create another" }).count()) === 1, `${tag} Create (ready): Give feedback next to Create another`);
    // Edit and the showcase: the inline panel took the button's place (SPEC-FEEDBACK-INLINE)
    await page.goto(`${base}/showcase/${CID}`, { waitUntil: "load" });
    await page.getByText("What v17 changed").first().waitFor({ timeout: 15000 });
    check(await enabledSoon(page.getByRole("button", { name: "Something is off" })), `${tag} Showcase detail: the feedback panel, enabled`);
    await page.goto(`${base}/edit?c=${CID}&v=13`, { waitUntil: "load" });
    await page.getByText("What changed").first().waitFor({ timeout: 15000 });
    check(await enabledSoon(page.getByRole("button", { name: "Something is off" })), `${tag} Edit workspace: the feedback panel, enabled`);

    // 2. the dialog from the Create result: context, defaults, focus kept inside, Esc closes
    const dlg = ready.locator("dialog[open]");
    if (createOk) await createBtn.click();
    await dlg.waitFor({ timeout: 5000 });
    const about = await dlg.locator("p", { hasText: /^About:/ }).innerText();
    check(
      (await dlg.getByText("What you write here is read by the person who tunes the engine. Nothing changes automatically.").count()) === 1 && about.includes(`· v${readyVersion.n} ·`) && about.includes("text to creative"),
      `${tag} dialog: the honesty line, context "${about.slice(0, 70)}…"`,
    );
    const pressed = async (name) => dlg.getByRole("button", { name, exact: true }).getAttribute("aria-pressed");
    check((await pressed("Something's wrong")) === "true" && (await pressed("something else")) === "true", `${tag} dialog defaults from a creative: wrong · something else`);
    check((await dlg.getByRole("button", { name: /of 5$/ }).count()) === 5, `${tag} dialog: five rating buttons`);
    await dlg.getByRole("button", { name: "This was good", exact: true }).click();
    check(
      (await dlg.getByText("What did you like?").count()) === 1 && (await dlg.getByText("What did you expect instead?").count()) === 0 && (await dlg.getByRole("button", { name: /of 5$/ }).count()) === 0,
      `${tag} dialog "good": What did you like?, no expected, no rating`,
    );
    await dlg.getByRole("button", { name: "Something's missing", exact: true }).click();
    await dlg.getByRole("button", { name: "the captions or the hook", exact: true }).click();
    await dlg.getByLabel("What happened?").fill("The hurry caption covered the board for ten seconds.");
    await dlg.getByLabel(/What did you expect instead/).fill("A short flash near the end.");
    await dlg.getByRole("button", { name: "3 of 5" }).click();
    check((await dlg.getByText("3/5").count()) === 1, `${tag} dialog: rating 3/5`);
    const inside = [];
    for (let i = 0; i < 30; i++) {
      await ready.keyboard.press("Tab");
      inside.push(await ready.evaluate(() => Boolean(document.activeElement?.closest("dialog[open]")) || document.activeElement === document.body));
    }
    check(inside.every(Boolean), `${tag} dialog: focus stays inside for 30 tabs`);
    // a modal: the viewport as the designer sees it, the dialog scrolled to its top (and, on a phone, to its end)
    await dlg.evaluate((d) => (d.scrollTop = 0));
    await ready.waitForTimeout(300);
    await ready.screenshot({ path: `qa/online-feedback-dialog-${vpName}.png`, scale: "css" });
    if (vpName === "390") {
      await dlg.evaluate((d) => (d.scrollTop = d.scrollHeight));
      await ready.waitForTimeout(300);
      await ready.screenshot({ path: `qa/online-feedback-dialog-end-390.png`, scale: "css" });
    }
    await ready.keyboard.press("Escape");
    await ready.waitForTimeout(200);
    check((await ready.locator("dialog[open]").count()) === 0, `${tag} dialog: Escape closes it`);
    await ready.close();
    const hdlg = page.locator("dialog[open]");

    // 3. the qa record from the header (general): defaults idea · website, no rating; the thanks line; the name remembered
    await page.evaluate((k) => localStorage.removeItem(k), NAME_KEY);
    await page.getByRole("button", { name: "Feedback about the studio" }).click();
    const hpressed = async (name) => hdlg.getByRole("button", { name, exact: true }).getAttribute("aria-pressed");
    await hdlg.waitFor({ timeout: 5000 });
    check((await hdlg.getByText("About: the studio").count()) === 1, `${tag} header dialog: About: the studio`);
    check((await hpressed("An idea")) === "true" && (await hpressed("the website itself")) === "true", `${tag} header dialog defaults: idea · the website itself`);
    check((await hdlg.getByRole("button", { name: /of 5$/ }).count()) === 0, `${tag} header dialog: no rating`);
    const send = hdlg.getByRole("button", { name: "Send", exact: true });
    check(await send.isDisabled(), `${tag} Send disabled until something is written`);
    await hdlg.getByLabel("Your name").fill(QA_RECORD.designer);
    await hdlg.getByLabel("What happened?").fill(QA_RECORD.wrong);
    const reqP = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname.endsWith("/api/feedback"));
    await send.click();
    const sent = (await reqP).postDataJSON();
    const sorted = (o) => JSON.stringify(Object.fromEntries(Object.entries(o).sort()));
    check(sorted(sent) === sorted(QA_RECORD), `${tag} the POST body is the qa record ${JSON.stringify(sent)}`);
    const thanks = hdlg.getByText(/^Thanks — saved as fb-/);
    await thanks.waitFor({ timeout: 15000 });
    const thanksText = await thanks.innerText();
    const savedId = /saved as (fb-[\w-]+)\./.exec(thanksText)?.[1];
    check(Boolean(savedId) && (await hdlg.getByText("Close", { exact: true }).count()) === 1 && (await hdlg.getByRole("button", { name: "Send another" }).count()) === 1, `${tag} thanks line: "${thanksText}"`);
    if (vpName === "1440") await page.screenshot({ path: `qa/online-feedback-dialog-thanks-1440.png`, scale: "css" });
    await hdlg.getByText("Close", { exact: true }).click();
    await page.getByRole("button", { name: "Feedback about the studio" }).click();
    check((await hdlg.getByLabel("Your name").inputValue()) === "qa", `${tag} the name is remembered`);
    await page.keyboard.press("Escape");

    // 4. Records
    await page.goto(base + "/feedback", { waitUntil: "load" });
    const list = page.getByRole("list", { name: "Feedback records, newest first" });
    await list.waitFor({ timeout: 15000 });
    const header = await page.getByText(/^\d+ records? from \d+ designers?$/).innerText();
    check(true, `${tag} records header "${header}"`);
    const rows = list.locator(":scope > li");
    const first = await rows.first().innerText();
    if (realFeedback && savedId && !savedId.endsWith("intercepted")) {
      check(first.includes(savedId) && first.includes(QA_RECORD.wrong), `${tag} the qa record is listed first (newest first)`);
    }
    const stamps = await rows.locator("time").evaluateAll((ts) => ts.map((t) => t.getAttribute("datetime")));
    check(stamps.every((t, i) => i === 0 || t <= stamps[i - 1]), `${tag} newest first (${stamps.length} rows)`);
    check((await list.getByRole("link", { name: /^Open v\d+/ }).first().getAttribute("href"))?.startsWith("/edit?c="), `${tag} Open v<N> links to /edit?c=…&v=…`);
    await shot(page, `online-feedback-records-${vpName}.png`);
    check((await overflow(page)) === 0, `${tag} records: no horizontal overflow`);
    await page.getByLabel("Designer").selectOption("Ben (test)");
    await page.waitForFunction(() => new URL(location.href).searchParams.get("designer") === "Ben (test)");
    await page.waitForTimeout(800);
    const designers = await rows.locator("span.text-label-md").allInnerTexts();
    check(designers.length > 0 && designers.every((d) => d === "Ben (test)"), `${tag} designer filter: ${designers.length} rows, all Ben (test), in the URL`);
    await page.getByLabel("Kind").selectOption("missing");
    await page.waitForTimeout(800);
    check((await rows.count()) === 1 && (await page.getByText("1 record matches the filters").count()) === 1, `${tag} kind filter narrows to one`);
    await page.getByRole("button", { name: "Clear the filters" }).click();
    await page.waitForTimeout(800);
    check(new URL(page.url()).search === "?tab=records" && (await rows.count()) >= 4, `${tag} filters cleared`);
    const creativeOpts = await page.getByLabel("This creative only").locator("option").allInnerTexts();
    check(creativeOpts.some((o) => o.startsWith("An easy Color Block Jam level")), `${tag} the creative filter shows titles`);
    if (vpName === "1440") {
      const dl = page.waitForEvent("download");
      await page.getByRole("button", { name: "Download .md" }).click();
      const file = await dl;
      const text = readFileSync(await file.path(), "utf8");
      check(/^feedback-\d{4}-\d{2}-\d{2}\.md$/.test(file.suggestedFilename()) && text.startsWith("# Designer feedback") && text.length > 100, `${tag} Download .md: ${file.suggestedFilename()}, ${text.length} chars`);
    }

    // 5. Lessons (fixture)
    await page.getByRole("tab", { name: "Lessons" }).click();
    await page.getByRole("heading", { name: /^Lessons v2/ }).waitFor({ timeout: 10000 });
    check(new URL(page.url()).searchParams.get("tab") === "lessons", `${tag} ?tab=lessons`);
    const partA = page.locator('section[aria-labelledby="part-a"]');
    const partB = page.locator('section[aria-labelledby="part-b"]');
    check(
      (await partA.locator("h3").count()) === 2 && (await partA.locator("ol > li").count()) === 3 && (await partA.getByText("Suggested change:").count()) === 3,
      `${tag} Part A: 2 workflow cards, 3 lessons with suggested changes`,
    );
    check((await partA.locator("h3").allInnerTexts()).join("|").toLowerCase() === "text to creative|the website", `${tag} Part A titles are workflow words`);
    check((await partA.getByText("strong", { exact: true }).count()) === 1 && (await partA.getByText("thin", { exact: true }).count()) === 2, `${tag} confidence chips`);
    check((await partB.locator("h3").count()) === 2 && (await partB.getByText("Asks for by default").count()) === 2, `${tag} Part B: 2 designers`);
    check((await page.getByRole("region", { name: "Open questions for the designers" }).locator("li").count()) === 2, `${tag} 2 open questions`);
    check((await page.getByRole("region", { name: "Owner corrections applied" }).locator("li").count()) === 1, `${tag} 1 correction applied`);
    check((await page.getByRole("region", { name: "Dropped by the checks" }).getByText(lessons.meta.dropped[0]).count()) === 1, `${tag} the dropped line`);
    check((await page.getByText("# LESSONS").count()) === 0, `${tag} the Markdown is not rendered`);
    check((await page.getByRole("button", { name: "Make this the current version" }).count()) === 0, `${tag} no rollback button on the current version`);
    await shot(page, `online-feedback-lessons-${vpName}.png`);
    check((await overflow(page)) === 0, `${tag} lessons: no horizontal overflow`);
    if (vpName === "1440") {
      const dl = page.waitForEvent("download");
      await page.getByRole("button", { name: "Download LESSONS.md" }).click();
      const file = await dl;
      check(readFileSync(await file.path(), "utf8") === lessons.markdown && file.suggestedFilename() === "LESSONS-v2.md", `${tag} Download LESSONS.md = the markdown field`);
    }
    // an old version → rollback
    const versionSel = page.getByLabel("Version");
    check((await versionSel.locator("option").count()) === 2, `${tag} version select has 2 versions`);
    await versionSel.selectOption("1");
    await page.getByRole("heading", { name: /^Lessons v1/ }).waitFor({ timeout: 10000 });
    const rollback = page.getByRole("button", { name: "Make this the current version" });
    check((await rollback.count()) === 1, `${tag} an old version shows "Make this the current version"`);
    if (vpName === "390") await shot(page, `online-feedback-lessons-old-390.png`);
    await rollback.click();
    await page.getByText("current", { exact: true }).waitFor({ timeout: 10000 });
    check(JSON.stringify(lessonPosts.at(-1)) === JSON.stringify({ action: "rollback", version: 1 }), `${tag} rollback posts ${JSON.stringify(lessonPosts.at(-1))}`);
    // a correction
    await versionSel.selectOption("2");
    await page.getByRole("heading", { name: /^Lessons v2/ }).waitFor({ timeout: 10000 });
    const corrText = "qa: the caption lesson is right; keep it.";
    await page.getByLabel("Correct a lesson in your words").fill(corrText);
    await page.getByRole("button", { name: "Apply correction" }).click();
    await page.waitForTimeout(250);
    check((await page.getByText("Reading the records… writing lessons").count()) === 1, `${tag} correcting: the waiting line`);
    await page.getByRole("heading", { name: /^Lessons v3/ }).waitFor({ timeout: 10000 });
    check(JSON.stringify(lessonPosts.at(-1)) === JSON.stringify({ action: "correct", text: corrText }), `${tag} correction posts {action: "correct", text}`);
    check((await versionSel.locator("option").count()) === 3 && (await page.getByLabel("Correct a lesson in your words").inputValue()) === "", `${tag} the new version shows, the select grows to 3`);
    // an evidence chip → the Records tab with that one record
    const ev = "fb-20261018-135100-44db";
    await partA.getByRole("button", { name: ev }).first().click();
    await page.getByText("Showing one record:").waitFor({ timeout: 10000 });
    const u = new URL(page.url());
    await page.waitForTimeout(800);
    check(u.searchParams.get("tab") === "records" && u.searchParams.get("id") === ev && (await rows.count()) === 1 && (await rows.first().innerText()).includes(ev), `${tag} evidence chip → Records with that one record`);
    if (vpName === "1440") await shot(page, `online-feedback-records-one-1440.png`);
    await page.getByRole("button", { name: "Show all" }).click();
    await page.waitForTimeout(800);
    check((await rows.count()) >= 4, `${tag} Show all`);
    // the empty state
    lessonsMode = "empty";
    await page.getByRole("tab", { name: "Lessons" }).click();
    const empty = await page.getByText("No lessons yet. Distill once there is feedback.").waitFor({ timeout: 10000 }).then(() => true, () => false);
    check(empty && (await page.getByRole("button", { name: "Distill now" }).isEnabled()), `${tag} empty state with Distill now`);
    if (vpName === "1440") await shot(page, `online-feedback-lessons-empty-1440.png`);

    check(lessonPosts.every((b) => b.action !== "distill"), `${tag} no distill was posted`);
    check(!posts.some((p) => /\/api\/(plan|make|direct|review|upload|preview|enhance|trends)$/.test(p)), `${tag} no workflow POSTs`);
    noErrors(errors, tag);
    await ctx.close();
  }
  check(!realFeedback || realPosts === 1, `real /api/feedback POSTs: ${realPosts}`);
}
