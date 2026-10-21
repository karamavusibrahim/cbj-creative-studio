// v2 (every function): a human-paced walkthrough of the live site, recorded as video (Playwright's recordVideo) for the final
// presentation. Real engine calls: one Enhance, one trend fetch, one link read, one full Generate (plan + Unity
// record + compose + review), one soundtrack with the spoken hook, one music edit, one caption edit, one feedback
// record, one Lessons distillation. A visible cursor is drawn by an injected overlay (Playwright videos have none).
//
//   node scripts/record-demo.mjs [https://cbj-creative-studio.vercel.app] [out-dir]
//
// Output: <out-dir>/demo-raw.webm, chapters.json (timestamps of each step and of the waits, for the cut).
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const SITE = process.argv[2] || "https://cbj-creative-studio.vercel.app";
const OUT = process.argv[3] || path.join(process.cwd(), "qa", "demo");
const PASSCODE = fs.readFileSync(path.join(process.cwd(), "..", ".site-passcode"), "utf8").trim();
const VP = { width: 1440, height: 900 };
fs.mkdirSync(OUT, { recursive: true });

const t0 = Date.now();
const marks = [];
const mark = (label, kind = "step") => {
  const t = (Date.now() - t0) / 1000;
  marks.push({ t: Math.round(t * 10) / 10, label, kind });
  console.log(`[${t.toFixed(1)}s] ${label}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const CURSOR = `
(() => {
  const d = document.createElement('div');
  d.id = '__cursor';
  d.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:30px;z-index:2147483647;pointer-events:none;transform:translate(-3px,-2px);transition:transform .05s linear;';
  d.innerHTML = '<svg width="22" height="30" viewBox="0 0 22 30"><path d="M2 2 L2 24 L8 18 L12 28 L16 26 L12 17 L20 17 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const r = document.createElement('div');
  r.style.cssText = 'position:fixed;width:36px;height:36px;border-radius:50%;border:3px solid #5b2bd6;z-index:2147483646;pointer-events:none;opacity:0;transform:translate(-50%,-50%) scale(.4);';
  const add = () => { if (!document.body) return requestAnimationFrame(add); document.body.append(d, r); };
  add();
  window.addEventListener('mousemove', (e) => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
  window.addEventListener('mousedown', (e) => {
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    r.animate([{ opacity: .9, transform: 'translate(-50%,-50%) scale(.4)' }, { opacity: 0, transform: 'translate(-50%,-50%) scale(1.3)' }], { duration: 450 });
  }, true);
})();`;

let browser;
try {
  browser = await chromium.launch({ channel: "chrome", headless: true });
  console.log("using Google Chrome (h264 playback)");
} catch {
  browser = await chromium.launch({ headless: true });
  console.log("using Playwright Chromium");
}
const ctx = await browser.newContext({ viewport: VP, deviceScaleFactor: 1, recordVideo: { dir: OUT, size: VP } });
await ctx.addInitScript(CURSOR);
const page = await ctx.newPage();
let mouse = { x: 700, y: 450 };

async function glide(x, y, ms = 600) {
  const steps = Math.max(12, Math.round(ms / 16));
  const sx = mouse.x, sy = mouse.y;
  for (let i = 1; i <= steps; i++) {
    const k = 0.5 - Math.cos((i / steps) * Math.PI) / 2; // ease in-out
    await page.mouse.move(sx + (x - sx) * k, sy + (y - sy) * k);
    await sleep(ms / steps);
  }
  mouse = { x, y };
}

async function bring(locator) {
  await locator.first().waitFor({ state: "visible", timeout: 60_000 });
  for (let i = 0; i < 40; i++) {
    const box = await locator.first().boundingBox();
    if (!box) break;
    const top = box.y, bottom = box.y + box.height;
    if (top >= 90 && bottom <= VP.height - 40) break;
    const dy = top < 90 ? -Math.min(160, 90 - top + 40) : Math.min(160, bottom - (VP.height - 40) + 40);
    await page.mouse.wheel(0, dy);
    await sleep(45);
  }
  await sleep(150);
}

async function click(locator, { pause = 900, label } = {}) {
  await bring(locator);
  const box = await locator.first().boundingBox();
  await glide(box.x + Math.min(box.width / 2, 160), box.y + box.height / 2);
  await sleep(180);
  await page.mouse.down();
  await sleep(70);
  await page.mouse.up();
  if (label) mark(label);
  await sleep(pause);
}

async function type(locator, text, { delay = 28 } = {}) {
  await click(locator, { pause: 250 });
  await page.keyboard.type(text, { delay });
  await sleep(500);
}

async function scrollBy(total, ms = 900) {
  const steps = Math.max(6, Math.round(ms / 40));
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, total / steps);
    await sleep(ms / steps);
  }
}

async function unlockIfAsked() {
  const field = page.getByLabel("Passcode");
  try {
    await field.waitFor({ state: "visible", timeout: 2500 });
  } catch {
    return;
  }
  mark("Passcode gate (the input is masked)");
  await type(field, PASSCODE, { delay: 60 });
  await click(page.getByRole("dialog").getByRole("button", { name: /unlock/i }), { label: "Unlocked" });
}

async function step(name, fn) {
  mark(name);
  try {
    await fn();
  } catch (e) {
    console.log(`  !! ${name}: ${e.message.split("\n")[0]}`);
    marks.push({ t: Math.round(((Date.now() - t0) / 1000) * 10) / 10, label: `FAILED: ${name}`, kind: "error" });
  }
}

const PROMPT_A = "Zor bir seviye, 45 saniye, bir bomba kırmızı blokları temizlesin, hook 'Can you beat it?'";
const PROMPT_B = "An easy CBJ level on a small open board with four blocks in three colours. The player almost fails and solves it with two seconds left. The hook says 'Can you beat it?'. 30 seconds.";
const LINK = "https://mapendo.co/blog/best-mobile-games-ads";

// ── the walkthrough (v2: every function) ─────────────────────────────────────────────────────────
await page.goto(SITE, { waitUntil: "networkidle" });
await page.mouse.move(mouse.x, mouse.y);
await page.getByText("Engine online").first().waitFor({ timeout: 60_000 });
mark("Create page, engine online");
await sleep(2500);

await step("0 · The header and the Help sheet (How it works, the edit contract)", async () => {
  await click(page.getByRole("button", { name: "Help" }), { pause: 1200, label: "Help: How it works" });
  await sleep(2500);
  await page.mouse.wheel(0, 500); await sleep(2500);
  await page.mouse.wheel(0, 500); await sleep(2500);
  await page.keyboard.press("Escape");
  await sleep(800);
});

await step("1 · Prompt enhancement (Turkish request with an impossible ask)", async () => {
  const box = page.getByRole("textbox").first();
  await type(box, PROMPT_A);
  await sleep(800);
  await click(page.getByRole("button", { name: "Enhance prompt" }), { pause: 300 });
  await unlockIfAsked();
  mark("wait: enhance", "wait");
  const region = page.getByRole("region", { name: "Enhanced request" });
  await region.waitFor({ timeout: 90_000 });
  mark("Enhanced: translated, the bomb replaced, questions offered");
  await bring(region);
  await sleep(6000);
  const option = region.getByRole("button").filter({ hasText: /\.$/ }).first();
  if (await option.count()) await click(option, { label: "One suggested sentence appended", pause: 2500 });
  await scrollBy(-400, 500);
});

await step("2 · Ideas from trends (optional) and from a link", async () => {
  const card = page.getByRole("region", { name: "Start from a trend" });
  await bring(card);
  await sleep(1200);
  await click(page.getByRole("button", { name: /Get (new )?ideas/ }), { pause: 300 });
  await unlockIfAsked();
  mark("wait: trends", "wait");
  await page.getByRole("button", { name: "Use this prompt" }).first().waitFor({ timeout: 120_000 });
  mark("Trend ideas written as prompts, with sources and the skipped list");
  await sleep(4000);
  await scrollBy(500, 1200);
  await sleep(2500);
  await scrollBy(-500, 900);
  const url = page.getByPlaceholder("https://…");
  await type(url, LINK, { delay: 12 });
  await click(page.getByRole("button", { name: "Read link" }), { pause: 300 });
  mark("wait: link", "wait");
  await page.getByText("From your link").first().waitFor({ timeout: 120_000 });
  mark("Ideas from the pasted link, above the feed ideas");
  await sleep(4500);
});

async function feedbackOnResult() {
  // a flag on a row pre-fills the step and the item; otherwise the panel itself
  const flag = page.getByRole("button", { name: /^Feedback about/ }).first();
  const panel = page.getByRole("region", { name: "Was this what you asked?" });
  if (await flag.count()) await click(flag, { pause: 1200, label: "A flag on a row opens the feedback panel, step and item pre-filled" });
  else await bring(panel);
  // a flag already chose "Something is off"; without a flag, choose it now
  const what = panel.getByLabel(/What happened\?|What did you like\?/).first();
  if (!(await what.isVisible().catch(() => false))) {
    const off = panel.getByRole("button", { name: "Something is off" }).first();
    if (await off.isVisible().catch(() => false)) await click(off, { pause: 800 });
  }
  await what.waitFor({ state: "visible", timeout: 15_000 });
  await type(what, "The hurry caption stays a little long on screen; the rest is as asked.");
  const name = panel.getByLabel(/Your name/).first();
  if (await name.count()) { await click(name, { pause: 200 }); await page.keyboard.press("Meta+A"); await page.keyboard.type("Demo designer", { delay: 40 }); }
  await click(panel.getByRole("button", { name: "Send", exact: true }), { pause: 300, label: "Send: tied to the step the row belongs to" });
  await page.getByText(/Thanks, saved as fb-/).first().waitFor({ timeout: 60_000 });
  await sleep(3500);
}

async function downloadReport(label) {
  const btn = page.getByRole("button", { name: "Download report" }).first();
  if (!(await btn.count())) return null;
  await bring(btn);
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 90_000 }), click(btn, { pause: 300, label })]);
  const file = path.join(OUT, dl.suggestedFilename());
  await dl.saveAs(file);
  mark(`Report saved: ${dl.suggestedFilename()}`);
  await sleep(1500);
  return file;
}

await step("3 · Generate a creative (plan, record in Unity, compose, review)", async () => {
  const box = page.getByRole("textbox").first();
  await bring(box);
  const clear = page.getByRole("button", { name: "Clear the prompt" });
  if (await clear.count()) await click(clear, { pause: 400 });
  else {
    await click(box, { pause: 200 });
    await page.keyboard.press("Meta+A");
    await page.keyboard.press("Backspace");
  }
  await type(box, PROMPT_B);
  await sleep(1000);
  const specs = page.getByText("Creative specifications").first();
  if (await specs.count()) { await bring(specs); mark("Creative specifications (optional): duration, format, difficulty, arc"); await sleep(3000); }
  const audioToggle = page.getByText("Audio (optional)").first();
  if (await audioToggle.count()) {
    await click(audioToggle, { pause: 900, label: "Audio (optional): bed + narration chosen before generating" });
    await click(page.getByRole("checkbox", { name: /Soundtrack bed/ }), { pause: 500 });
    await click(page.getByRole("checkbox", { name: /Narrate the captions/ }), { pause: 1200 });
  }
  const more = page.getByRole("button", { name: "More", exact: true });
  if (await more.count()) { await click(more, { pause: 1500, label: "More: Level only, draft, review and revise switches" }); }
  await click(page.getByRole("button", { name: "Generate creative" }), { pause: 300 });
  await unlockIfAsked();
  mark("wait: plan", "wait");
  const understood = page.getByText("Set by the prompt").first();
  await understood.waitFor({ timeout: 420_000 });
  mark("The plan: what the planner understood for each control");
  await bring(understood);
  await sleep(2500);
  await scrollBy(450, 1500);
  await sleep(5000);
  await scrollBy(-450, 900);
  mark("wait: make", "wait");
  const again = page.getByRole("button", { name: "Create another" });
  await again.waitFor({ timeout: 600_000 });
  mark("Ready: the finished creative, with audio");
  await sleep(1500);
  const chip = page.getByText("With audio").first();
  if (await chip.count()) { await bring(chip); await sleep(3500); }
  const video = page.locator("video").first();
  await bring(video);
  await video.evaluate((v) => { v.muted = true; v.currentTime = 0; return v.play(); }).catch(() => {});
  mark("Playing the ad");
  await sleep(14_000);
  const checks = page.getByText("Checks from the recording").first();
  if (await checks.count()) { await bring(checks); mark("Level & gameplay: the checks, measured from the recording and the level file"); await sleep(5000); }
  const viewer = page.getByRole("region", { name: "As a viewer" }).first();
  if (await viewer.count()) { await bring(viewer); mark("As a viewer: measured scores apart from the model's"); await sleep(5000); await scrollBy(400, 1200); await sleep(3000); }
  try { await feedbackOnResult(); } catch (e) { console.log("  !! feedback panel: " + e.message.split("\n")[0]); }
  try { await downloadReport("Download report (the intermediate steps as one file)"); } catch (e) { console.log("  !! report: " + e.message.split("\n")[0]); }
});

const UPLOADS = path.resolve(process.cwd(), "..", "studio", "uploads");

async function guided(label, file, prompt, { readyTimeout = 720_000 } = {}) {
  const again = page.getByRole("button", { name: "Create another" });
  if (await again.isVisible().catch(() => false)) await click(again, { pause: 1500, label: "Create another" });
  if (!(await page.locator('input[type="file"]').first().count())) {
    await page.goto(SITE, { waitUntil: "networkidle" });  // recover a page left in another state
    await page.getByText("Engine online").first().waitFor({ timeout: 60_000 });
    await sleep(1500);
  }
  const box = page.getByRole("textbox").first();
  await bring(box);
  await page.locator('input[type="file"]').first().setInputFiles(path.join(UPLOADS, file));
  await page.getByText(file, { exact: false }).first().waitFor({ timeout: 120_000 });
  mark(`Attached ${file}`);
  await sleep(2000);
  await type(box, prompt);
  await sleep(1000);
  await click(page.getByRole("button", { name: "Generate creative" }), { pause: 300 });
  await unlockIfAsked();
  mark(`wait: plan (${label})`, "wait");
  const understood = page.getByText("Set by the prompt").first();
  await understood.waitFor({ timeout: 300_000 });
  mark(`The plan: what was read from the ${label} and what the prompt set`);
  await bring(understood);
  await sleep(2500);
  const ref = page.getByRole("region", { name: "Reference to creative" }).first();
  if (await ref.count()) { await bring(ref); mark(`Reference to creative: what was read, adapted and not copied from the ${label}`); await sleep(5000); }
  await scrollBy(450, 1500);
  await sleep(4000);
  await scrollBy(-450, 900);
  mark(`wait: make (${label})`, "wait");
  await again.waitFor({ timeout: readyTimeout });
  mark(`Ready: the ${label}-guided creative`);
  await sleep(1500);
  const video = page.locator("video").first();
  await bring(video);
  await video.evaluate((v) => { v.muted = true; v.currentTime = 0; return v.play(); }).catch(() => {});
  await sleep(12_000);
  await scrollBy(600, 1600);
  await sleep(4000);
  await scrollBy(600, 1600);
  await sleep(4000);
  await scrollBy(600, 1600);
  await sleep(3000);
}

await step("3b · Image-guided creative: a reference picture read for the board and the look", async () => {
  await guided("picture", "T3_magical_garden.png",
    "Inspired by this image: a board shaped like it with the same block colours, and its soft garden colours for the background. Stop the ad before the last two blocks leave. 40 seconds.");
});

await step("3c · Video-guided creative: the video's own board, fewer blocks", async () => {
  await guided("video", "cbj_trailer_2.mp4",
    "Use the same game design and the same scenario as this video, just use fewer blocks. 30 seconds.");
});

await step("4 · The Soundtrack card: another bed or narration can be made at any time", async () => {
  const region = page.getByRole("region", { name: "Soundtrack", exact: true });
  await bring(region);
  await sleep(4000);
});

async function newVersionAfter(fn, label) {
  const tabs = page.getByRole("tablist", { name: "Versions" }).getByRole("tab");
  const before = await tabs.count();
  await fn();
  mark(`wait: ${label}`, "wait");
  await page.waitForFunction((n) => document.querySelectorAll('[role="tablist"][aria-label="Versions"] [role="tab"]').length > n, before, { timeout: 300_000 });
  await sleep(1500);
}

await step("5 · Controlled editing, the designer's view: one caption, then Before / after", async () => {
  const link = page.locator('a[href^="/edit?c="]').first();
  await click(link, { pause: 500, label: "Open in the Edit workspace" });
  await page.getByRole("region", { name: "Things in this ad" }).waitFor({ timeout: 60_000 });
  await sleep(2500);
  await scrollBy(300, 1000);
  await sleep(2000);
  const edit = page.getByRole("button", { name: "Edit text" }).first();
  await click(edit, { pause: 600 });
  const input = page.getByRole("region", { name: "Things in this ad" }).locator("input").first();
  await click(input, { pause: 200 });
  await page.keyboard.press("Meta+A");
  await page.keyboard.type("Beat the clock!", { delay: 40 });
  await sleep(500);
  await newVersionAfter(() => click(page.getByRole("button", { name: "Apply", exact: true }), { pause: 300, label: "Apply the caption edit (in code, no model)" }), "caption edit");
  mark("What changed: Locked, Allowed, Forbidden");
  const changed = page.getByText(/What v\d+ changed from v\d+/).first();
  await bring(changed);
  await sleep(7000);
  const pair = page.getByRole("tab", { name: "Before / after" }).first();
  if (await pair.count()) {
    await click(pair, { pause: 800, label: "Before / after" });
    const both = page.getByRole("button", { name: "Play both" }).first();
    if (await both.count()) { await click(both, { pause: 300 }); await sleep(10_000); }
  }
});

await step("5b · Details: the full checklist, the frames, Compare, metadata", async () => {
  const sw = page.getByRole("switch", { name: /Details/ }).first();
  if (await sw.count()) await click(sw, { pause: 1200, label: "Details on" });
  else await click(page.getByRole("button", { name: /^Details/ }).first(), { pause: 1200, label: "Details on" });
  const checklist = page.getByText("Checklist").first();
  if (await checklist.count()) { await bring(checklist); await sleep(4000); }
  const frames = page.getByText(/frames changed/).first();
  if (await frames.count()) { await bring(frames); mark("Frames changed, and every changed pixel inside the edited layers' boxes"); await sleep(4000); }
  const compare = page.getByRole("region", { name: "Compare" }).first();
  if (await compare.count()) { await bring(compare); mark("Compare any two versions"); await sleep(3000); }
  await scrollBy(500, 1400);
  await sleep(3000);
});

await step("5c · A direct asset edit: replace one picture, the report proves the rest", async () => {
  const things = page.getByRole("region", { name: "Things in this ad" });
  await bring(things);
  const replace = things.getByRole("button", { name: "Replace" }).first();
  if (!(await replace.count())) throw new Error("no Replace button");
  await newVersionAfter(async () => {
    const [fc] = await Promise.all([page.waitForEvent("filechooser", { timeout: 30_000 }), click(replace, { pause: 300, label: "Replace a picture with a file" })]);
    await fc.setFiles(path.join(UPLOADS, "T5_space_station.png"));
  }, "picture edit");
  mark("The new version's report: only the picture changed");
  await bring(page.getByText(/What v\d+ changed from v\d+/).first());
  await sleep(6000);
  const file = await downloadReport("Download report of this edit");
  if (file) {
    await page.goto("file://" + file, { waitUntil: "load" });
    mark("The report, opened: request, reading, steps, checks, edit report, review, files");
    await sleep(3000); await scrollBy(700, 2000); await sleep(3000); await scrollBy(700, 2000); await sleep(2500);
    await page.goBack({ waitUntil: "networkidle" });
    await page.getByRole("region", { name: "Things in this ad" }).waitFor({ timeout: 60_000 });
    await sleep(1500);
  }
  const music = page.getByText("More: music").first();
  if (await music.count()) { await click(music, { pause: 1500, label: "More: music (the soundtrack from the Edit page)" }); await sleep(3500); }
});

await step("6 · The owner's page: records, what the engine did, Analyze, Lessons", async () => {
  await click(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Feedback" }), { pause: 500, label: "The owner's Feedback page" });
  await unlockIfAsked();
  await page.getByText(/records? from \d+ designers?/).first().waitFor({ timeout: 60_000 });
  await sleep(3500);
  const did = page.getByRole("button", { name: "What the engine did" }).first();
  if (await did.count()) { await click(did, { pause: 1200, label: "What the engine did at that step: facts and log lines" }); await sleep(4500); }
  const an = page.getByRole("button", { name: "Analyze what happened" }).first();
  if (await an.count()) {
    await click(an, { pause: 300, label: "Analyze what happened" });
    mark("wait: analyze", "wait");
    await page.getByRole("button", { name: "Analyze again" }).first().waitFor({ timeout: 180_000 });
    mark("Analysis: what, why, the system or taste, quotes from the evidence only");
    await sleep(7000);
  }
  await click(page.getByRole("tab", { name: "Lessons" }), { pause: 1200 });
  await click(page.getByRole("button", { name: "Distill now" }), { pause: 300, label: "Distill the records into lessons" });
  mark("wait: distill", "wait");
  await page.getByRole("heading", { name: /^Lessons v\d/ }).first().waitFor({ timeout: 180_000 });
  mark("LESSONS: per workflow and per designer, with evidence, versions and rollback");
  await sleep(4000);
  await scrollBy(500, 1600);
  await sleep(4000);
  await scrollBy(500, 1600);
  await sleep(3000);
});

await step("7 · Your keys: run the studio on your own accounts", async () => {
  await click(page.getByRole("button", { name: /^Your keys/ }).first(), { pause: 1500, label: "Your keys: a Gemini key and the planner choice, per request, never stored" });
  const dialog = page.getByRole("dialog");
  await sleep(3000);
  const mine = dialog.getByText("My Anthropic key").first();
  if (await mine.count()) { await click(mine, { pause: 1500 }); await sleep(2000); }
  const studio = dialog.getByText("This studio's planner").first();
  if (await studio.count()) await click(studio, { pause: 800 });
  await click(dialog.getByRole("button", { name: "Cancel" }), { pause: 800 });
});

await step("8 · Showcase: finished creatives with their evidence, available offline", async () => {
  await click(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Showcase" }), { pause: 1500 });
  await page.locator('a[href^="/showcase/"]').first().waitFor({ timeout: 60_000 });
  await scrollBy(500, 1800);
  await sleep(1500);
  await scrollBy(-500, 900);
  await click(page.locator('a[href^="/showcase/"]').first(), { pause: 1500, label: "A showcase creative" });
  await sleep(2000);
  await scrollBy(600, 1800);
  await sleep(3000);
  await scrollBy(600, 1800);
  await sleep(3000);
});

mark("End");
await sleep(1500);
const videoPath = await page.video().path();
await ctx.close();
await browser.close();
const raw = path.join(OUT, "demo-raw.webm");
fs.renameSync(videoPath, raw);
fs.writeFileSync(path.join(OUT, "chapters.json"), JSON.stringify({ site: SITE, started: new Date(t0).toISOString(), marks }, null, 1));
console.log(`video: ${raw}\nchapters: ${path.join(OUT, "chapters.json")}`);
