// Playwright QA (SPEC §9.5): fresh context per check, 1440x900 and 390x844, overflow, page errors,
// console errors, full-page screenshots into qa/.  Usage: node scripts/qa.mjs <label> [base] [--real-enhance]
// Then the SPEC-ENHANCE §4 checks: the Enhance button and the trend card (online: present, button states,
// the Enhanced card and the idea cards rendered from scripts/fixtures/ — real engine answers saved once —
// served with page.route so the run spends no model call; offline: no Enhance enabled, no trend card),
// and the keyboard path; §2b, ideas from a link (fixture trends-link: the engine's real answer for
// mapendo.co; an engine 400 served by interception must show its detail verbatim under the field). --real-enhance also posts ONE real /api/enhance ("An easy level, calm, 30 seconds.").
// Then the SPEC-FEEDBACK §5 checks (label online | offline | locked): the four Give feedback entry points, the dialog,
// the owner's /feedback page (Records live from the engine; Lessons from scripts/fixtures/lessons.json by interception:
// no POST /api/lessons ever reaches the engine). --real-feedback posts ONE real /api/feedback (the qa record), else
// that POST is intercepted too. --feedback-only skips the earlier checks; "locked" runs only the feedback checks.
// Then the SPEC-SOUNDTRACK §4 checks (scripts/qa-soundtrack.mjs; online | offline): the card in Edit and on a ready Create
// page, the 502 path, the voice-less engine, "Use as the music" (its /api/direct answered in the browser). --real-soundtrack
// sends ONE real POST /api/soundtrack (voice: false, v3), else the saved answer; --soundtrack-only runs only these.
// Then SPEC-SOUNDTRACK §5-§6 (scripts/qa-audio.mjs): the Audio (optional) section of the Generate card, the make's `audio`
// (/api/plan, /api/make and the job answered in the browser: no real make), the ready state with audio_added.
// Then SPEC-FEEDBACK-INLINE §6 (scripts/qa-feedback-inline.mjs; online | offline): the inline panel on Create and Edit, the
// rows' flags, the designer's Edit workspace and Details, Download report, the owner's evidence and Analyze. With
// --real-feedback its ONE real POST /api/feedback (designer "qa-inline") is the only real one; --inline-only runs just these.
// Then SPEC-OWN-KEYS §4 / SPEC-OWN-ENGINE-2 (scripts/qa-keys.mjs; online): the dialog's Gemini-key mode, the stores, the one
// header (a fake key only, never an Anthropic key or a planner; every
// workflow POST answered or aborted in the browser), the pill, an older engine, offline, and the relay on a stand-in engine
// (--no-relay skips that part); --keys-only runs just these.
// Then SPEC-OWN-ENGINE §4 (scripts/qa-own-engine.mjs; online): "My own engine" against a fake engine at 127.0.0.1:8765
// answered by routing (the dialog, Check and its failures, the pill, calls on the own URL and none through the relay, no
// passcode, media on the own host, offline, Clear); --own-engine-only runs just these.
// Then SPEC-R2-CATALOGUE (scripts/qa-catalogue.mjs; online | offline): the gallery with the catalogue's creatives
// appended, a catalogue detail page, the 404 state and an unreachable bucket, against https://catalogue.test answered by
// routing (the build must be made with NEXT_PUBLIC_CATALOGUE_URL=https://catalogue.test; without it only the "off"
// checks run). Every context here serves that fixture bucket, so a catalogue build logs no failed request on the other
// pages either. --catalogue-only runs just these.
// Then SPEC-SAMPLE-ASSETS (scripts/qa-sample-assets.mjs; online | offline): the "Sample assets" link and its sheet on Create
// and Edit from the fixture bucket's assets/index.json (3 items), Attach as a dropped file (every POST /api/upload answered
// in the browser), the role badges, a failed download, an unreadable index; offline, the link disabled. Same build as the
// catalogue checks. --sample-assets-only runs just these.
import { chromium } from "playwright";
import { serveCatalogue } from "./qa-catalogue.mjs";
import { mkdirSync, readFileSync } from "node:fs";

const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const label = args[0] || "online";
const base = args[1] || "http://localhost:3105";
const realEnhance = process.argv.includes("--real-enhance");
const realFeedback = process.argv.includes("--real-feedback");
const realSoundtrack = process.argv.includes("--real-soundtrack");
const soundtrackOnly = process.argv.includes("--soundtrack-only");
const noFeedback = process.argv.includes("--no-feedback"); // skip the feedback checks (their Records list needs a record on the engine)
const inlineOnly = process.argv.includes("--inline-only"); // only the SPEC-FEEDBACK-INLINE checks
const keysOnly = process.argv.includes("--keys-only"); // only the SPEC-OWN-KEYS checks
const ownEngineOnly = process.argv.includes("--own-engine-only"); // only the SPEC-OWN-ENGINE checks
const catalogueOnly = process.argv.includes("--catalogue-only"); // only the SPEC-R2-CATALOGUE checks
const sampleAssetsOnly = process.argv.includes("--sample-assets-only"); // only the SPEC-SAMPLE-ASSETS checks
const explicitFeedbackOnly = process.argv.includes("--feedback-only");
const feedbackOnly = explicitFeedbackOnly || label === "locked" || soundtrackOnly || inlineOnly || keysOnly || ownEngineOnly || catalogueOnly || sampleAssetsOnly;
const CID = "1015-074810-create-a-hard-color-block";
const PAGES = [
  ["create", "/", "Create a new creative"],
  ["edit-picker", "/edit", "Edit a creative"],
  ["edit-v13", `/edit?c=${CID}&v=13`, "What changed"],
  ["showcase", "/showcase", "Finished creatives"],
  ["showcase-detail", `/showcase/${CID}`, "What v17 changed"],
];
const VIEWPORTS = [
  ["1440", { width: 1440, height: 900 }],
  ["390", { width: 390, height: 844 }],
];
mkdirSync("qa", { recursive: true });
const browser = await chromium.launch();
let failures = 0;
for (const [vpName, vp] of feedbackOnly ? [] : VIEWPORTS) {
  for (const [name, path, marker] of PAGES) {
    const ctx = await browser.newContext({ viewport: vp });
    await serveCatalogue(ctx);
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() !== "error") return;
      const t = m.text();
      if (/play\(\)|NotAllowedError|AbortError/.test(t)) return;
      errors.push(`console: ${t}`);
    });
    await page.goto(base + path, { waitUntil: "load" });
    try {
      await page.getByText(marker, { exact: false }).first().waitFor({ timeout: 15000 });
    } catch {
      errors.push(`marker not found: ${marker}`);
    }
    await page.waitForTimeout(2500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const status = await page.locator('[role="status"]').first().innerText().catch(() => "");
    const file = `qa/${label}-${name}-${vpName}.png`;
    await page.screenshot({ path: file, fullPage: true, scale: "css" });
    const ok = overflow === 0 && errors.length === 0;
    if (!ok) failures++;
    console.log(`${ok ? "OK  " : "FAIL"} ${label} ${vpName} ${name}: overflow=${overflow} status="${status.trim()}" ${errors.length ? "\n     " + errors.join("\n     ") : ""}`);
    await ctx.close();
  }
}

// ── SPEC-ENHANCE §4 ────────────────────────────────────────────────────────────────────────────────
const fixture = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8"));
function check(ok, what) {
  if (!ok) failures++;
  console.log(`${ok ? "OK  " : "FAIL"} ${label} ${what}`);
}
async function featurePage(vp) {
  const ctx = await browser.newContext({ viewport: vp });
  await serveCatalogue(ctx);
  const page = await ctx.newPage();
  const errors = [];
  const posts = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !/play\(\)|NotAllowedError|AbortError/.test(m.text())) errors.push(`console: ${m.text()}`);
  });
  page.on("request", (r) => {
    if (r.method() === "POST") posts.push(new URL(r.url()).pathname);
  });
  return { ctx, page, errors, posts };
}
const enhanceBtn = (page) => page.getByRole("button", { name: /Enhance prompt|Reading your request/ });
const trendCard = (page) => page.getByRole("region", { name: "Start from a trend" });

if (feedbackOnly) {
  /* only the feedback checks below */
} else if (label === "offline") {
  const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
  await page.goto(base + "/", { waitUntil: "load" });
  await page.getByText("Engine offline").first().waitFor({ timeout: 15000 });
  await page.fill("#prompt", "An easy level, calm, 30 seconds.");
  check(await enhanceBtn(page).isDisabled(), "offline: Enhance prompt is disabled");
  check((await page.locator('span[title="Needs the engine"]').filter({ has: enhanceBtn(page) }).count()) === 1, 'offline: Enhance carries the "Needs the engine" tooltip');
  check((await trendCard(page).count()) === 0, "offline: no trend card");
  check((await page.getByRole("button", { name: "Read link" }).count()) === 0, "offline: no link field");
  await page.goto(`${base}/edit?c=${CID}&v=13`, { waitUntil: "load" });
  await page.getByText("What changed").first().waitFor({ timeout: 15000 });
  check(await enhanceBtn(page).isDisabled(), "offline: Edit's Enhance prompt is disabled");
  check(errors.length === 0, `offline: no page/console errors ${errors.join("; ")}`);
  await ctx.close();
} else {
  const changed = fixture("enhance-changed");
  const trends = fixture("trends");
  const linked = fixture("trends-link");
  const LINK_400 = "that page could not be read (paywalled, login-only, a social feed or heavy scripts); try a public article link";
  for (const [vpName, vp] of VIEWPORTS) {
    const { ctx, page, errors, posts } = await featurePage(vp);
    let served400 = 0; // the browser logs each intercepted 400 as a failed resource; those are expected
    await page.route("**/api/enhance", (r) => r.fulfill({ json: changed }));
    await page.route("**/api/trends", async (r) => {
      const body = r.request().postDataJSON() || {};
      if (!body.url) return r.fulfill({ json: trends });
      await new Promise((ok) => setTimeout(ok, 800)); // long enough to see the waiting state
      if (/instagram/.test(body.url)) return served400++, r.fulfill({ status: 400, json: { detail: LINK_400 } });
      return r.fulfill({ json: linked });
    });
    await page.goto(base + "/", { waitUntil: "load" });
    await page.locator('[role="status"]').filter({ hasText: "Online" }).first().waitFor({ timeout: 15000 });
    await trendCard(page).waitFor({ timeout: 10000 }).catch(() => null);
    const tag = `${vpName} create:`;
    check(await enhanceBtn(page).isDisabled(), `${tag} Enhance disabled with an empty prompt`);
    check((await trendCard(page).count()) === 1, `${tag} the trend card is shown (collapsed)`);
    check((await page.getByRole("button", { name: "Get ideas" }).count()) === 1 && (await page.getByLabel("Ideas from trends").count()) === 0, `${tag} collapsed: Get ideas, no ideas fetched`);
    check(!posts.some((p) => p.endsWith("/api/trends") || p.endsWith("/api/enhance")), `${tag} nothing fetched on load`);

    // enhance (fixture: a real changed answer): the text becomes the rewrite, the helper chips are cleared
    const mine = "Zor bir seviye yap, bir bomba bir satırı temizlesin, make it pop. 45 saniye. Only 1% can solve it!";
    await page.fill("#prompt", mine);
    await page.getByRole("button", { name: "Hard", exact: true }).click();
    check(!(await enhanceBtn(page).isDisabled()), `${tag} Enhance enabled with text`);
    await enhanceBtn(page).click();
    const card = page.getByRole("region", { name: "Enhanced request" });
    await card.waitFor({ timeout: 10000 });
    check((await page.inputValue("#prompt")) === changed.prompt, `${tag} the textarea holds the rewrite`);
    check((await page.getByRole("button", { name: /Remove “A hard level\.”/ }).count()) === 0, `${tag} helper chips cleared`);
    check((await card.getByRole("list", { name: "What was changed" }).locator("li").count()) === changed.changes.length, `${tag} ${changed.changes.length} change rows in a <ul>`);
    check((await card.locator("s").first().innerText()) === changed.changes[0].before, `${tag} 'before' struck through`);
    check((await card.getByText("Will be read as:").count()) === 1, `${tag} the workflow line`);
    const opt = card.getByRole("button", { name: "Captions in English." });
    await opt.click();
    check((await page.inputValue("#prompt")) === `${changed.prompt} Captions in English.` && (await opt.getAttribute("aria-pressed")) === "true", `${tag} an option appends its sentence and is marked added`);
    await page.waitForTimeout(400); // the chip's colour transition
    await page.screenshot({ path: `qa/${label}-create-enhanced-${vpName}.png`, fullPage: true, scale: "css" });
    await opt.click();
    check((await page.inputValue("#prompt")) === changed.prompt && (await opt.getAttribute("aria-pressed")) === "false", `${tag} a second tap removes exactly that sentence`);
    await card.getByRole("button", { name: "Undo" }).click();
    check((await page.inputValue("#prompt")) === mine && (await page.getByRole("button", { name: /Remove “A hard level\.”/ }).count()) === 1, `${tag} Undo restores the text and the chips`);
    await enhanceBtn(page).click();
    await card.waitFor({ timeout: 10000 });

    // trends (fixture: a real /api/trends answer)
    await page.getByRole("button", { name: "Get ideas" }).click();
    const ideas = page.getByLabel("Ideas from trends").locator("li");
    await ideas.first().waitFor({ timeout: 10000 });
    check((await ideas.count()) === trends.ideas.length, `${tag} ${trends.ideas.length} idea cards`);
    await page.getByText(`Skipped (${trends.skipped.length})`).click();
    await page.waitForTimeout(400);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(overflow === 0, `${tag} no horizontal overflow with both cards open (${overflow})`);
    await page.screenshot({ path: `qa/${label}-create-trends-${vpName}.png`, fullPage: true, scale: "css" });

    // §2b ideas from a link: button states, an engine 400 under the field, then the link's ideas above the feed's
    const readBtn = page.getByRole("button", { name: "Read link" });
    const urlField = page.getByLabel("Or paste a link to an article, a post or a trend page");
    check(await readBtn.isDisabled(), `${tag} Read link disabled with an empty field`);
    const [fieldBox, btnBox] = [await urlField.boundingBox(), await readBtn.boundingBox()];
    const stacked = btnBox.y >= fieldBox.y + fieldBox.height - 1;
    check(vpName === "390" ? stacked : !stacked, `${tag} the link row ${vpName === "390" ? "stacks" : "is one row"}`);
    await urlField.fill("https://www.instagram.com/p/abc");
    check(!(await readBtn.isDisabled()), `${tag} Read link enabled with text`);
    await readBtn.click();
    await page.waitForTimeout(150);
    check(
      (await page.getByText("Reading the page… writing ideas").count()) === 1 && (await readBtn.isDisabled()) && (await page.getByRole("button", { name: "Get new ideas" }).isDisabled()),
      `${tag} reading: status line, both buttons disabled`,
    );
    const linkErr = page.locator("#trend-link-error");
    await linkErr.waitFor({ timeout: 10000 });
    check((await linkErr.innerText()) === LINK_400 && (await urlField.getAttribute("aria-describedby")) === "trend-link-error", `${tag} the engine's 400 shown verbatim under the field`);
    check((await ideas.count()) === trends.ideas.length, `${tag} a failed link keeps the feed ideas`);
    await urlField.fill(linked.link);
    await readBtn.click();
    await page.getByText("From your link").first().waitFor({ timeout: 10000 });
    const n = linked.ideas.length;
    check((await ideas.count()) === n + trends.ideas.length && (await linkErr.count()) === 0, `${tag} ${n} link ideas added to the ${trends.ideas.length} feed ideas, error cleared`);
    check(
      (await ideas.nth(0).getByText("From your link").count()) === 1 && (await ideas.nth(n).getByText("From your link").count()) === 0 && (await ideas.nth(0).locator("h3").innerText()) === linked.ideas[0].title,
      `${tag} the link ideas come first, each with "From your link"`,
    );
    check((await ideas.nth(0).locator(`a[href="${linked.link}"][target="_blank"]`).count()) === 1, `${tag} the link idea's source is the URL`);
    check((await page.getByText(/^From mapendo\.co · read /).count()) === 1 && (await page.getByText(`Skipped (${linked.skipped.length})`).count()) === 1, `${tag} the link footer and its Skipped`);
    const overflowLink = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(overflowLink === 0, `${tag} no horizontal overflow with the link ideas (${overflowLink})`);
    await page.screenshot({ path: `qa/${label}-create-trends-link-${vpName}.png`, fullPage: true, scale: "css" });
    const unstick = await page.addStyleTag({ content: "header { position: static !important; }" }); // or it covers the card's top
    await trendCard(page).screenshot({ path: `qa/${label}-trend-card-link-${vpName}.png`, scale: "css" });
    await unstick.evaluate((el) => el.remove());

    if (vpName === "1440") {
      // keyboard: Tab reaches Enhance, Undo, every option chip, Read link, Use this prompt
      await page.locator("body").focus();
      await page.evaluate(() => (document.activeElement)?.blur());
      const seen = new Set();
      for (let i = 0; i < 110; i++) {
        await page.keyboard.press("Tab");
        seen.add(await page.evaluate(() => (document.activeElement?.textContent || "").trim()));
      }
      const want = ["Enhance prompt", "Undo", ...changed.questions.flatMap((q) => q.options), "Read link", "Use this prompt"];
      const missing = want.filter((w) => ![...seen].some((s) => s.includes(w)));
      check(missing.length === 0, `keyboard: Tab reaches Enhance, Undo, ${want.length - 4} option chips, Read link, Use this prompt${missing.length ? " MISSING " + missing.join(" | ") : ""}`);
    }

    // Use this prompt over existing text: asks first, then replaces and focuses the prompt (a link idea, then a feed idea)
    for (const [i, want, what] of [[0, linked.ideas[0].prompt, "link"], [linked.ideas.length, trends.ideas[0].prompt, "feed"]]) {
      await ideas.nth(i).getByRole("button", { name: "Use this prompt" }).click();
      await page.getByRole("group", { name: "Replace your text?" }).getByRole("button", { name: "Replace" }).click();
      await page.waitForTimeout(300);
      check((await page.inputValue("#prompt")) === want && (await page.evaluate(() => document.activeElement?.id)) === "prompt", `${tag} Use this prompt (Replace) on a ${what} idea fills and focuses the prompt`);
    }
    check(!posts.some((p) => /\/api\/(plan|make|direct|review|upload|preview)$/.test(p)), `${tag} no workflow POSTs`);
    const failed400 = errors.filter((e) => /status of 400/.test(e));
    const unexpected = errors.filter((e) => !/status of 400/.test(e)).concat(failed400.slice(served400));
    check(unexpected.length === 0, `${tag} no page/console errors (besides ${served400} intercepted 400) ${unexpected.join("; ")}`);
    await ctx.close();
  }

  {
    const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
    await page.goto(`${base}/edit?c=${CID}&v=13`, { waitUntil: "load" });
    await page.getByText("What changed").first().waitFor({ timeout: 15000 });
    check((await enhanceBtn(page).count()) === 1 && (await enhanceBtn(page).isDisabled()), "edit: Enhance present, disabled while the box is empty");
    await page.fill("#edit-prompt", "make the hook yellow");
    check(!(await enhanceBtn(page).isDisabled()), "edit: Enhance enabled with text");
    check(errors.length === 0, `edit: no page/console errors ${errors.join("; ")}`);
    await ctx.close();
  }

  if (realEnhance) {
    // the one allowed real call (~15 s): the card must render from the engine's own answer
    const { ctx, page, errors, posts } = await featurePage({ width: 1440, height: 900 });
    await page.goto(base + "/", { waitUntil: "load" });
    await page.locator('[role="status"]').filter({ hasText: "Online" }).first().waitFor({ timeout: 15000 });
    await page.fill("#prompt", "An easy level, calm, 30 seconds.");
    await enhanceBtn(page).click();
    check((await page.getByText("Reading your request…").count()) === 1, "real enhance: the waiting state");
    const card = page.getByRole("region", { name: "Enhanced request" });
    await card.waitFor({ timeout: 90000 }).catch(() => null);
    const text = (await card.innerText().catch(() => "")).replace(/\s+/g, " ");
    check(/Your request is already clear\.|nothing was added/.test(text) && text.includes("Will be read as:"), `real enhance: card rendered: ${text.slice(0, 160)}…`);
    await page.screenshot({ path: `qa/${label}-create-enhanced-real-1440.png`, fullPage: true, scale: "css" });
    check(posts.filter((p) => p.endsWith("/api/enhance")).length === 1, "real enhance: exactly one POST");
    check(errors.length === 0, `real enhance: no page/console errors ${errors.join("; ")}`);
    await ctx.close();
  }
}

// --real-feedback: the one real record is the inline panel's (designer "qa-inline"), unless only the dialog's checks run
if (!keysOnly && !ownEngineOnly && !catalogueOnly && !sampleAssetsOnly) {
  if (!soundtrackOnly && !noFeedback && !inlineOnly) {
    await import("./qa-feedback.mjs").then((m) => m.default({ browser, base, label, check, featurePage, VIEWPORTS, CID, realFeedback: realFeedback && explicitFeedbackOnly }));
  }
  if (!soundtrackOnly && label !== "locked" && !explicitFeedbackOnly) {
    await import("./qa-feedback-inline.mjs").then((m) => m.default({ browser, base, label, check, featurePage, VIEWPORTS, CID, realFeedback }));
  }
  if (inlineOnly) {
    /* only the inline checks */
  } else if (label !== "locked") await import("./qa-soundtrack.mjs").then((m) => m.default({ browser, base, label, check, featurePage, VIEWPORTS, CID, realSoundtrack }));
  if (label !== "locked" && !inlineOnly) await import("./qa-audio.mjs").then((m) => m.default({ browser, base, label, check, featurePage, VIEWPORTS }));
}
if (keysOnly || (label === "online" && !feedbackOnly)) {
  await import("./qa-keys.mjs").then((m) => m.default({ browser, base, label, check, featurePage, VIEWPORTS, CID, relay: !process.argv.includes("--no-relay") }));
}

if (ownEngineOnly || (label === "online" && !feedbackOnly)) {
  await import("./qa-own-engine.mjs").then((m) => m.default({ browser, base, label, check, featurePage, VIEWPORTS, CID }));
}

if (catalogueOnly || (label !== "locked" && !feedbackOnly)) {
  await import("./qa-catalogue.mjs").then((m) => m.default({ browser, base, check, VIEWPORTS, only: catalogueOnly }));
}

if (sampleAssetsOnly || (label !== "locked" && !feedbackOnly)) {
  await import("./qa-sample-assets.mjs").then((m) => m.default({ browser, base, label, check, VIEWPORTS, CID, only: sampleAssetsOnly }));
}

await browser.close();
console.log(failures ? `${failures} check(s) failed` : "all checks passed");
process.exit(failures ? 1 : 0);
