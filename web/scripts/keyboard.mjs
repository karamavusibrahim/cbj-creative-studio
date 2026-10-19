// Keyboard check (SPEC §9.6): tab through the Create page; with a passcode set, Generate opens the
// unlock dialog and focus stays inside it. Never submits a passcode; every workflow POST is aborted in the
// browser, and the Generate step is skipped when no passcode is set (it would plan for real).
import { chromium } from "playwright";
const base = process.argv[2] || "http://localhost:3105";
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const posts = [];
page.on("request", (r) => { if (r.method() === "POST") posts.push(r.url()); });
await page.route(/\/api\/(plan|make|preview|review|direct|upload|enhance|trends)$/, (r) => (r.request().method() === "POST" ? r.abort() : r.continue()));
await page.goto(base + "/", { waitUntil: "load" });
await page.getByText("Engine online").waitFor({ timeout: 15000 });
await page.fill("#prompt", "A test prompt (not sent).");
await page.evaluate(() => document.activeElement?.blur());
const seen = [];
for (let i = 0; i < 60; i++) {
  await page.keyboard.press("Tab");
  seen.push(await page.evaluate(() => { const e = document.activeElement; return `${e.tagName.toLowerCase()}:${(e.getAttribute("aria-label") || e.textContent || e.id || "").trim().slice(0, 40)}`; }));
}
console.log("tab order:\n  " + seen.join("\n  "));
for (const want of ["Enhance prompt", "Get ideas", "Beat the clock", "Which side first?", "30 sec", "16:9", "Hard", "Generate creative", "Plan only", "More"]) {
  console.log(`${seen.some((s) => s.includes(want)) ? "reached " : "MISSING "} ${want}`);
}
const session = await page.evaluate(() => fetch("/api/session").then((r) => r.json()));
if (!session.required) {
  console.log("no passcode set: the unlock-dialog step is skipped (Generate would plan for real)");
  console.log(`POSTs made: ${posts.length ? posts.join(", ") : "none"}`);
  await browser.close();
  process.exit(0);
}
await page.fill("#prompt", "A test prompt (not sent).");
await page.getByRole("button", { name: "Generate creative" }).click();
const dlg = page.locator("dialog[open]");
await dlg.waitFor({ timeout: 5000 });
const inside = [];
for (let i = 0; i < 8; i++) {
  await page.keyboard.press("Tab");
  inside.push(await page.evaluate(() => !!document.activeElement?.closest("dialog") || document.activeElement === document.body));
}
console.log(`dialog open; focus stayed inside for 8 tabs: ${inside.every(Boolean)} (${inside.join(",")})`);
await page.screenshot({ path: "qa/locked-unlock-dialog-1440.png", scale: "css" });
await page.keyboard.press("Escape");
console.log(`dialog closed on Escape: ${(await page.locator("dialog[open]").count()) === 0}`);
console.log(`POSTs made: ${posts.length ? posts.join(", ") : "none"}`);
await browser.close();
