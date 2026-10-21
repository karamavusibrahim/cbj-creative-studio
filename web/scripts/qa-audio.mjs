// SPEC-SOUNDTRACK §5 (audio at creation time) and §6 (narration), run from qa.mjs (it passes the browser and its check()).
// Online: the "Audio (optional)" section in the Generate card renders collapsed; opening it shows the two boxes; the
// choice is remembered across pages; Generate posts /api/plan and /api/make, BOTH answered here (no real plan or make
// ever reaches the engine: every other workflow POST is aborted), and the make's body carries `audio`; the job is
// answered from scripts/fixtures/job-make-audio.json (a v2 with audio_added.from_version: 1, written by hand from the
// spec's shape over the real music-edit version v4 of READY_CID) with a running "audio" stage first; the ready state shows
// the With audio chip, the description, the spoken lines, and the review of v1 with the spec's line. An engine whose meta
// says voice: false: the narrate box disabled with its tooltip; a bed-only make through Plan only → Make it; a draft sends
// no audio. An engine without the feature: no section. voice_skipped: the amber line. Offline: no section.
import { readFileSync } from "node:fs";

const fixture = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8"));
const READY_CID = "1018-110841-an-easy-color-block-jam";
import { engineJson } from "./qa-engine.mjs";
const NO_VOICE_TIP = "The engine has no voice (NVIDIA key or the voice extra)";
const HELP = "Added after the creative is made, as a music edit you can see in the version history. Nothing else changes.";
const REVIEW_LINE = "Reviewed as v1, before the audio was added (the audio edit kept every frame)";
const WORKFLOW = /\/api\/(plan|make|preview|direct|review|upload|enhance|trends|lessons|feedback|soundtrack)$/;
const PROMPT = "An easy CBJ level, calm, 30 seconds.";

export default async function audioChecks({ browser, base, label, check, featurePage, VIEWPORTS }) {
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const section = (page) => page.getByRole("group", { name: "Audio (optional)", exact: true });
  const toggle = (page) => section(page).getByRole("button", { name: /^Audio \(optional\)/ });
  const shot = async (loc, file) => {
    const page = loc.page();
    await page.waitForTimeout(400);
    const unstick = await page.addStyleTag({ content: "header { position: static !important; }" });
    await loc.screenshot({ path: `qa/${file}`, scale: "css" });
    await unstick.evaluate((el) => el.remove());
  };
  const noErrors = (errors, what) => check(errors.length === 0, `${what}: no page/console errors ${errors.join("; ")}`);

  if (label === "offline") {
    const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
    await page.goto(base + "/", { waitUntil: "load" });
    await page.getByText("Engine offline").first().waitFor({ timeout: 15000 });
    await page.waitForTimeout(800);
    check((await section(page).count()) === 0 && (await page.getByText("Audio (optional)").count()) === 0, "offline /: no Audio (optional) section");
    noErrors(errors, "offline audio");
    await ctx.close();
    return;
  }

  const job = fixture("job-make-audio");
  const added = job.result.audio_added;
  const versions = await engineJson(`/api/creatives/${READY_CID}`);
  const brief = versions.find((x) => x.n === 1).brief; // the plan job is answered with v1's real brief

  /** /api/plan and /api/make are answered here; any other workflow POST is aborted before the engine. */
  async function guard(page, result = job.result) {
    const log = { plan: [], make: [], aborted: [], polls: 0 };
    await page.route("**/api/**", (r) => {
      const req = r.request();
      if (req.method() === "POST" && WORKFLOW.test(new URL(req.url()).pathname)) {
        log.aborted.push(new URL(req.url()).pathname);
        return r.abort();
      }
      return r.fallback();
    });
    await page.route("**/api/plan", (r) => {
      log.plan.push(r.request().postDataJSON());
      return r.fulfill({ json: { job: "qa-plan" } });
    });
    await page.route("**/api/jobs/qa-plan*", (r) =>
      r.fulfill({ json: { id: "qa-plan", kind: "plan", status: "done", stage: "done", lines: [{ t: 0.2, stage: "plan", text: "qa: the plan is answered by the test" }], n_lines: 1, result: brief, elapsed: 1 } }),
    );
    await page.route("**/api/make", (r) => {
      log.make.push(r.request().postDataJSON());
      return r.fulfill({ json: { job: "qa-make-audio" } });
    });
    await page.route("**/api/jobs/qa-make-audio*", (r) => {
      // three polls in the audio stage first, so the running strip can be seen; then the finished job
      if (log.polls++ < 3) {
        const lines = job.lines.filter((l) => l.t < 99.25);
        return r.fulfill({ json: { ...job, status: "running", stage: "plan", lines, n_lines: lines.length, result: null, elapsed: 99.3 } });
      }
      return r.fulfill({ json: { ...job, result } });
    });
    return log;
  }

  for (const [vpName, vp] of VIEWPORTS) {
    const tag = `${vpName} audio:`;
    const { ctx, page, errors } = await featurePage(vp);
    const log = await guard(page);
    await page.goto(base + "/", { waitUntil: "load" });
    const gen = page.getByRole("region", { name: "Generate", exact: true });
    const sec = section(page);
    const shown = await sec.waitFor({ timeout: 15000 }).then(() => true, () => false);
    check(shown && (await gen.locator(sec).count()) === 1, `${tag} the section is inside the Generate card`);
    const [sBox, bBox] = [await sec.boundingBox(), await gen.getByRole("button", { name: "Generate creative" }).boundingBox()];
    check(sBox && bBox && sBox.y + sBox.height <= bBox.y + 1, `${tag} above the Generate button`);
    check((await toggle(page).getAttribute("aria-expanded")) === "false" && (await sec.getByRole("checkbox").count()) === 0 && sBox.height < 60, `${tag} collapsed to one row (${Math.round(sBox.height)} px), "Off"`);
    await shot(gen, `${label}-audio-collapsed-${vpName}.png`);

    await toggle(page).click();
    const bed = sec.getByRole("checkbox", { name: "Soundtrack bed from the concept" });
    const narrate = sec.getByRole("checkbox", { name: "Narrate the captions" });
    check((await sec.getByRole("checkbox").count()) === 2 && !(await bed.isChecked()) && !(await narrate.isChecked()) && (await narrate.isEnabled()), `${tag} open: the two boxes, both off`);
    check((await sec.getByText(HELP).count()) === 1, `${tag} the help line`);
    await bed.check();
    await narrate.check();
    const narr = sec.getByRole("group", { name: "What is narrated" });
    check((await narr.getByRole("button", { name: "All captions" }).getAttribute("aria-pressed")) === "true", `${tag} All captions by default`);
    check((await sec.getByLabel("Voice").inputValue()) === "Magpie-Multilingual.EN-US.Mia" && (await sec.getByLabel("Different first line").getAttribute("placeholder")) === "the hook caption", `${tag} the voice (Mia) and Different first line (placeholder "the hook caption")`);
    check((await toggle(page).innerText()).includes("Bed + narration"), `${tag} the collapsed row says what is on`);
    if (vpName === "1440") {
      await toggle(page).focus();
      const seen = [];
      for (let i = 0; i < 6; i++) {
        await page.keyboard.press("Tab");
        seen.push(await page.evaluate(() => { const a = document.activeElement; return `${a?.tagName.toLowerCase()}:${(a?.textContent || "").trim()}`; }));
      }
      check(seen[0] === "input:" && seen[1] === "input:" && seen[2].endsWith("All captions") && seen[3].endsWith("Hook only") && seen[4].startsWith("select:") && seen[5] === "input:", `keyboard audio: Tab → ${seen.join(" → ")}`);
    }
    check((await overflow(page)) === 0, `${tag} no horizontal overflow (open)`);
    await shot(gen, `${label}-audio-open-${vpName}.png`);

    // remembered for the session: away to the Showcase and back through the header nav (state in memory, not storage)
    await page.getByRole("link", { name: "Showcase", exact: true }).first().click();
    await page.getByText("Finished creatives").first().waitFor({ timeout: 15000 });
    await page.getByRole("link", { name: "Create", exact: true }).first().click();
    await section(page).waitFor({ timeout: 15000 });
    await toggle(page).click();
    check((await bed.isChecked()) && (await narrate.isChecked()), `${tag} the choice is remembered across pages`);
    check((await page.evaluate(() => JSON.stringify({ ...localStorage }).includes("narration"))) === false, `${tag} …and not stored`);
    await sec.getByLabel("Different first line").fill("Ready for this?");

    // Generate → plan → make, both answered here
    await page.fill("#prompt", PROMPT);
    await page.getByRole("button", { name: "Generate creative" }).click();
    await page.getByText("Adding the audio…").first().waitFor({ timeout: 15000 });
    const strip = page.getByRole("list", { name: "Stages" });
    check((await strip.locator('[aria-current="step"]').innerText()).trim() === "Adding the audio…", `${tag} running: the audio stage is on ("Adding the audio…") although the edit's lines name earlier stages`);
    const m = log.make[0] || {};
    check(log.plan.length === 1 && log.make.length === 1 && m.prompt === PROMPT && m.review === true && m.revise === true && m.draft === false, `${tag} Generate posted /api/plan then /api/make (both answered here)`);
    check(
      JSON.stringify(m.audio) === JSON.stringify({ bed: true, voice: true, voice_name: "Magpie-Multilingual.EN-US.Mia", narration: "captions", line: "Ready for this?" }),
      `${tag} /api/make carries audio ${JSON.stringify(m.audio)}`,
    );

    // ready: the version WITH audio
    await page.getByText("With audio", { exact: true }).waitFor({ timeout: 15000 });
    const creative = page.getByRole("region", { name: "Creative", exact: true });
    check((await creative.getByText(added.description, { exact: true }).count()) === 1, `${tag} the audio_added description under the player`);
    const spoken = (await creative.getByRole("list", { name: "What is said" }).locator("li").allInnerTexts()).map((x) => x.replace(/\s+/g, " ").trim());
    check(JSON.stringify(spoken) === JSON.stringify(added.voice.lines.map((l) => `${Math.round(l.at_s * 10) / 10} s · “${l.text}”`)), `${tag} the spoken lines: ${spoken.join(" | ")}`);
    check((await page.locator("video").first().getAttribute("src"))?.includes(`/${READY_CID}/v4/`) && (await page.getByText("Brief of v2").count()) === 1, `${tag} the version shown is the result (v2, with audio)`);
    const review = page.getByRole("region", { name: "As a viewer" });
    await review.getByText(/Ready to ship|Worth a fix/).first().waitFor({ timeout: 15000 });
    check((await review.getByText(REVIEW_LINE, { exact: true }).count()) === 1, `${tag} the review line names v1`);
    check((await review.getByRole("link", { name: "review.json" }).getAttribute("href")).endsWith(`/${READY_CID}/v1/review.json`), `${tag} the review shown is v1's`);
    check((await strip.locator("li").allInnerTexts()).join(",") === "plan,level,play,record,compose,review,revise,audio,done", `${tag} the strip lists the audio stage`);
    check((await page.getByRole("region", { name: "Soundtrack", exact: true }).count()) === 1, `${tag} the Soundtrack card stays available`);
    check(log.aborted.length === 0, `${tag} no other workflow POST ${log.aborted.join(", ")}`);
    check((await overflow(page)) === 0, `${tag} no horizontal overflow (ready)`);
    await shot(creative, `${label}-audio-ready-${vpName}.png`);
    await page.screenshot({ path: `qa/${label}-create-audio-ready-${vpName}.png`, fullPage: true, scale: "css" });
    noErrors(errors, tag);
    await ctx.close();
  }

  // ── voice: false → the box disabled; bed only through Plan only → Make it; a draft sends no audio ─────
  {
    const tag = "1440 audio, no voice:";
    const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
    const log = await guard(page, { ...job.result, audio_added: { ...added, voice: null, voice_skipped: "no hook caption to speak" } });
    await page.route("**/api/meta", async (r) => {
      const j = await (await r.fetch()).json();
      return r.fulfill({ json: { ...j, features: { ...(j.features || {}), soundtrack: { bed: true, voice: false } } } });
    });
    await page.goto(base + "/", { waitUntil: "load" });
    await section(page).waitFor({ timeout: 15000 });
    await page.waitForTimeout(800);
    await toggle(page).click();
    const narrate = section(page).getByRole("checkbox", { name: "Narrate the captions" });
    check((await narrate.isDisabled()) && (await section(page).locator(`span[title="${NO_VOICE_TIP}"]`).filter({ has: page.getByRole("checkbox", { name: "Narrate the captions" }) }).count()) === 1, `${tag} Narrate the captions disabled with "${NO_VOICE_TIP}"`);
    await section(page).getByRole("checkbox", { name: "Soundtrack bed from the concept" }).check();
    await page.getByRole("button", { name: "More", exact: true }).click();
    await page.getByRole("checkbox", { name: /^Draft/ }).check();
    check((await section(page).getByText("A draft is made without the audio").count()) === 1, `${tag} draft: the section says the audio is skipped`);
    await page.fill("#prompt", PROMPT);
    await page.getByRole("button", { name: "Plan only" }).click();
    await page.getByRole("button", { name: "Make it" }).waitFor({ timeout: 15000 });
    check((await page.getByText("Audio after the make").count()) === 0, `${tag} draft: no "Audio after the make" line`);
    await page.getByRole("button", { name: "Back to the prompt" }).click();
    const draft = page.getByRole("checkbox", { name: /^Draft/ });
    if (!(await draft.isVisible())) await page.getByRole("button", { name: "More", exact: true }).click();
    await draft.uncheck();
    await page.getByRole("button", { name: "Plan only" }).click();
    await page.getByRole("button", { name: "Make it" }).waitFor({ timeout: 15000 });
    check((await page.getByText("Audio after the make: a soundtrack bed from the concept.").count()) === 1, `${tag} planned: "Audio after the make" line`);
    await page.getByRole("button", { name: "Make it" }).click();
    await page.getByText("With audio", { exact: true }).waitFor({ timeout: 15000 });
    check(log.make.length === 1 && JSON.stringify(log.make[0].audio) === JSON.stringify({ bed: true, voice: false }), `${tag} Make it posts audio ${JSON.stringify(log.make[0]?.audio)}`);
    check((await page.getByText("Voice skipped: no hook caption to speak").count()) === 1 && (await page.getByRole("list", { name: "What is said" }).count()) === 0, `${tag} voice_skipped: the amber line, no spoken lines`);
    check(log.aborted.length === 0, `${tag} no other workflow POST ${log.aborted.join(", ")}`);
    noErrors(errors, tag);
    await ctx.close();
  }

  // ── a draft make sends no audio; an engine without the feature has no section ──────────────────────
  {
    const tag = "1440 audio, draft:";
    const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
    const log = await guard(page, versions.find((x) => x.n === 1));
    await page.goto(base + "/", { waitUntil: "load" });
    await section(page).waitFor({ timeout: 15000 });
    await toggle(page).click();
    await section(page).getByRole("checkbox", { name: "Soundtrack bed from the concept" }).check();
    await page.getByRole("button", { name: "More", exact: true }).click();
    await page.getByRole("checkbox", { name: /^Draft/ }).check();
    await page.fill("#prompt", PROMPT);
    await page.getByRole("button", { name: "Generate creative" }).click();
    await page.getByText("Generation complete").first().waitFor({ timeout: 15000 });
    check(log.make.length === 1 && log.make[0].draft === true && !("audio" in log.make[0]), `${tag} no audio sent with a draft`);
    check((await page.getByText("With audio", { exact: true }).count()) === 0 && (await page.getByText("before the audio was added").count()) === 0, `${tag} a version without audio_added: no chip, the normal review`);
    noErrors(errors, tag);
    await ctx.close();
  }
  {
    const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
    await page.route("**/api/meta", async (r) => {
      const j = await (await r.fetch()).json();
      const { soundtrack: _drop, ...f } = j.features || {};
      void _drop;
      return r.fulfill({ json: { ...j, features: f } });
    });
    await page.goto(base + "/", { waitUntil: "load" });
    await page.getByRole("button", { name: "Generate creative" }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(1500);
    check((await section(page).count()) === 0, "meta without features.soundtrack: no Audio section");
    noErrors(errors, "audio no feature");
    await ctx.close();
  }
}
