// SPEC-SOUNDTRACK §4, run from qa.mjs (it passes the browser and its check()). Online: the card in the Edit workspace
// (creative READY_CID v3) and on a ready Create page (the finished make answered by interception, as the feedback
// checks do); ONE real POST /api/soundtrack without voice with --real-soundtrack (else scripts/fixtures/soundtrack.json,
// the engine's real answer for v3, saved once); every POST with voice: true is answered here (it would call the TTS
// service), and so is the 502 path; "Use as the music" posts /api/direct, answered here and its body asserted. The voice
// checkbox disabled with its tooltip when /api/meta says voice: false (intercepted); hidden on an engine without the
// feature. Offline: no card. Keyboard: Tab reaches the checkbox, the select, both buttons. Screenshots at 1440 and 390.
// §6: "Narrate the captions" (All captions / Hook only → narration), "Different first line"; a voiced answer from
// scripts/fixtures/soundtrack-voice.json (written by hand, 3 lines; never the TTS) lists the spoken lines with their times.
import { readFileSync } from "node:fs";

const fixture = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8"));
const READY_CID = "1018-110841-an-easy-color-block-jam";
import { ENGINE, engineJson } from "./qa-engine.mjs";
const NO_VOICE_TIP = "The engine has no voice (NVIDIA key or the voice extra)";
const NARRATE_TIP = "NVIDIA Magpie speaks each caption of this creative as it appears";
const LINE_HELP = "Replaces the hook's words; the other captions are read as written.";
const TTS_502 = "the voice could not be made: RpcError: qa: the TTS service is answered by the test";
const WORKFLOW = /\/api\/(plan|make|preview|direct|review|upload|enhance|trends|lessons|feedback)$/;

export default async function soundtrackChecks({ browser, base, label, check, featurePage, VIEWPORTS, CID, realSoundtrack }) {
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const card = (page) => page.getByRole("region", { name: "Soundtrack", exact: true });
  const cardShot = async (page, file) => {
    await page.waitForTimeout(400);
    const unstick = await page.addStyleTag({ content: "header { position: static !important; }" }); // or it covers the card's top
    await card(page).screenshot({ path: `qa/${file}`, scale: "css" });
    await unstick.evaluate((el) => el.remove());
  };
  // a version without a viewer review answers 404 for its review.json (the review card asks for it): allowed, one per such response
  const missingReviews = new WeakMap();
  const watch404 = (page) => {
    missingReviews.set(page, 0);
    page.on("response", (r) => r.status() === 404 && /\/review\.json$/.test(r.url()) && missingReviews.set(page, missingReviews.get(page) + 1));
  };
  const noErrors = (errors, what, allow = /$^/, page = null) => {
    let left = page ? missingReviews.get(page) || 0 : 0;
    const bad = errors.filter((e) => !allow.test(e) && !(/status of 404/.test(e) && left-- > 0));
    check(bad.length === 0, `${what}: no page/console errors ${bad.join("; ")}`);
  };

  // ── offline ─────────────────────────────────────────────────────────────────────────────────────
  if (label === "offline") {
    const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
    for (const [path, marker] of [
      ["/", "Engine offline"],
      [`/edit?c=${CID}&v=13`, "What changed"],
    ]) {
      await page.goto(base + path, { waitUntil: "load" });
      await page.getByText(marker).first().waitFor({ timeout: 15000 });
      await page.waitForTimeout(800);
      check((await card(page).count()) === 0 && (await page.getByText("Soundtrack (optional)").count()) === 0, `offline ${path}: no soundtrack card`);
    }
    noErrors(errors, "offline soundtrack");
    await ctx.close();
    return;
  }

  const st = fixture("soundtrack");
  const sv = fixture("soundtrack-voice");
  const versions = await engineJson(`/api/creatives/${READY_CID}`);
  const v3 = versions.find((x) => x.n === 3);
  const v4 = versions.find((x) => x.n === 4); // stands in for the version the music edit would make
  const hook = v3.brief?.concept?.hook || "";
  const wantFollows = ["bright major, 84 bpm", `${st.concept.exits.length} block exits → plucks`, "ending: clean win", `${st.seconds} s`];
  let realSent = 0;

  /** Every soundtrack and direct POST is decided here; a guard aborts any other workflow POST before the engine. */
  async function guard(page) {
    const log = { soundtrack: [], direct: [], real: 0, aborted: [], tts502: 0, voiced: 0 };
    watch404(page);
    await page.route("**/api/**", (r) => {
      const req = r.request();
      if (req.method() === "POST" && WORKFLOW.test(new URL(req.url()).pathname)) {
        log.aborted.push(new URL(req.url()).pathname);
        return r.abort();
      }
      return r.fallback();
    });
    await page.route("**/api/soundtrack", async (r) => {
      const body = r.request().postDataJSON() || {};
      log.soundtrack.push(body);
      await new Promise((ok) => setTimeout(ok, 600)); // long enough to see the waiting line
      if (body.voice === true) {
        // never the TTS service: the first voiced request fails here (the 502 path), the next ones get the hand-written voice
        if (log.tts502 === 0) {
          log.tts502++;
          return r.fulfill({ status: 502, json: { detail: TTS_502 } });
        }
        log.voiced++;
        return r.fulfill({ json: sv });
      }
      if (realSoundtrack && realSent === 0 && body.creative_id === READY_CID && body.version === 3) {
        realSent++;
        log.real++;
        return r.continue();
      }
      return r.fulfill({ json: st });
    });
    await page.route("**/api/direct", (r) => {
      log.direct.push(r.request().postDataJSON());
      return r.fulfill({ json: { job: "qa-direct" } });
    });
    await page.route("**/api/jobs/qa-direct*", (r) =>
      r.fulfill({ json: { id: "qa-direct", kind: "direct", status: "done", stage: "done", lines: [{ t: 0.4, stage: "compose", text: "qa: the music edit is answered by the test" }], n_lines: 1, result: v4, elapsed: 1 } }),
    );
    return log;
  }

  async function makeAndCheck(page, tag) {
    const c = card(page);
    await c.getByRole("button", { name: "Make the soundtrack" }).click();
    await page.waitForTimeout(150);
    check((await c.getByText("Writing the bed…", { exact: true }).count()) === 1 && (await c.getByRole("button", { name: "Make the soundtrack" }).isDisabled()), `${tag} waiting: "Writing the bed…", button disabled`);
    const audio = c.locator("audio");
    await audio.waitFor({ timeout: 15000 });
    const src = await audio.getAttribute("src");
    check(src === `${ENGINE}/studio/uploads/${st.file}` && src.endsWith(".wav") && (await audio.getAttribute("controls")) !== null, `${tag} <audio controls> from the engine: ${src}`);
    check((await c.locator(`a[download="${st.file}"]`).innerText()).trim() === st.file, `${tag} download link with the file name`);
    check((await c.locator("p", { hasText: st.description }).count()) === 1, `${tag} the description paragraph`);
    const follows = await c.getByRole("list", { name: "What it follows" }).locator("li").allInnerTexts();
    check(JSON.stringify(follows) === JSON.stringify(wantFollows), `${tag} what it follows: ${follows.join(" · ")}`);
    const playable = await audio.evaluate((a) => new Promise((ok) => (a.readyState >= 1 ? ok(a.duration) : a.addEventListener("loadedmetadata", () => ok(a.duration), { once: true }), setTimeout(() => ok(a.duration), 8000))));
    check(Math.abs(playable - st.seconds) < 0.5, `${tag} the WAV loads in the browser (${playable} s)`);
    return audio;
  }

  for (const [vpName, vp] of VIEWPORTS) {
    // ── Edit workspace ────────────────────────────────────────────────────────────────────────────
    {
      const tag = `${vpName} soundtrack edit:`;
      const { ctx, page, errors } = await featurePage(vp);
      const log = await guard(page);
      await page.goto(`${base}/edit?c=${READY_CID}&v=3`, { waitUntil: "load" });
      await page.getByText("What changed").first().waitFor({ timeout: 15000 });
      await page.getByText("More: music", { exact: true }).click(); // folded in the designer's Edit workspace
      const c = card(page);
      const shown = await c.waitFor({ timeout: 15000 }).then(() => true, () => false);
      check(shown && (await c.getByText("Soundtrack (optional)").count()) === 1, `${tag} the card is shown`);
      const things = await page.getByRole("region", { name: "Things in this ad" }).boundingBox();
      const box = await c.boundingBox();
      check(things && box && box.y > things.y + things.height - 1 && Math.abs(box.x - things.x) < 2, `${tag} directly below "Things in this ad"`);
      const voice = c.getByRole("checkbox", { name: "Narrate the captions" });
      check(!(await voice.isChecked()) && (await voice.isEnabled()), `${tag} Narrate the captions: off by default, enabled (the engine has a voice)`);
      check((await c.locator(`span[title="${NARRATE_TIP}"]`).filter({ has: page.getByRole("checkbox", { name: "Narrate the captions" }) }).count()) === 1, `${tag} Narrate the captions: tooltip "${NARRATE_TIP}"`);
      check((await c.getByText("Speak the hook").count()) === 0 && (await c.getByText("Say this instead").count()) === 0, `${tag} the old wording is gone`);
      check((await c.getByLabel("Voice").count()) === 0, `${tag} no voice select while it is off`);
      check(log.soundtrack.length === 0, `${tag} nothing made on load`);
      await cardShot(page, `${label}-soundtrack-edit-collapsed-${vpName}.png`);

      // the voice options (never sent with voice: true to the engine: the 502 path is answered here)
      await voice.check();
      const sel = c.getByLabel("Voice");
      const opts = await sel.locator("option").allInnerTexts();
      check((await sel.inputValue()) === "Magpie-Multilingual.EN-US.Mia" && opts[0] === "Mia" && opts.includes("Mia, calm") && opts.includes("Jason, neutral") && opts.length === 18, `${tag} voice select: default Mia, ${opts.length} short names`);
      const first = c.getByLabel("Different first line");
      check((await first.getAttribute("placeholder")) === (hook || "Type the words to speak"), `${tag} Different first line: the hook caption as placeholder ("${hook}")`);
      check((await first.evaluate((el) => document.getElementById(el.getAttribute("aria-describedby"))?.textContent?.trim())) === LINE_HELP, `${tag} Different first line: its help "${LINE_HELP}"`);
      const narr = c.getByRole("group", { name: "What is narrated" });
      const pressed = async () => narr.getByRole("button").evaluateAll((bs) => bs.map((b) => `${b.textContent}:${b.getAttribute("aria-pressed")}`).join(","));
      check((await pressed()) === "All captions:true,Hook only:false", `${tag} All captions (default) / Hook only: ${await pressed()}`);
      if (vpName === "1440") {
        // keyboard: from the card title, Tab reaches the checkbox, both narration choices, the select, the field, Make the soundtrack
        await c.getByText("Soundtrack (optional)").click();
        const seen = [];
        for (let i = 0; i < 6; i++) {
          await page.keyboard.press("Tab");
          seen.push(await page.evaluate(() => { const a = document.activeElement; return `${a?.tagName.toLowerCase()}:${a?.getAttribute("type") || ""}:${(a?.textContent || "").trim()}`; }));
        }
        check(
          seen[0] === "input:checkbox:" && seen[1].endsWith("All captions") && seen[2].endsWith("Hook only") && seen[3].startsWith("select:") && seen[4] === "input::" && seen[5].endsWith("Make the soundtrack"),
          `keyboard soundtrack: Tab → ${seen.join(" → ")}`,
        );
        await cardShot(page, `${label}-soundtrack-edit-narrate-${vpName}.png`);
      }
      await c.getByRole("button", { name: "Make the soundtrack" }).click();
      await page.waitForTimeout(150);
      check((await c.getByText("Writing the bed… and the voice").count()) === 1, `${tag} waiting with the voice: "…and the voice"`);
      await c.getByText(TTS_502).waitFor({ timeout: 10000 });
      check((await c.getByRole("alert").innerText()).includes(TTS_502), `${tag} 502: the detail verbatim`);
      check((await c.getByRole("button", { name: "Make it without the voice" }).count()) === 1, `${tag} 502: "Make it without the voice" offered`);
      const asked = log.soundtrack[log.soundtrack.length - 1];
      check(
        JSON.stringify(asked) === JSON.stringify({ creative_id: READY_CID, version: 3, voice: true, voice_name: "Magpie-Multilingual.EN-US.Mia", narration: "captions" }),
        `${tag} the voiced request (answered here): ${JSON.stringify(asked)}`,
      );
      if (vpName === "1440") await cardShot(page, `${label}-soundtrack-edit-502-${vpName}.png`);

      // without the voice: the one real call (1440, --real-soundtrack), else the fixture
      await c.getByRole("button", { name: "Make it without the voice" }).click();
      await c.locator("audio").waitFor({ timeout: 15000 });
      const plain = log.soundtrack[log.soundtrack.length - 1];
      check(plain.voice === false && !("voice_name" in plain) && plain.version === 3, `${tag} without the voice: ${JSON.stringify(plain)}`);
      check((await c.getByRole("alert").count()) === 0, `${tag} the error is cleared`);
      // Make another: back to the collapsed state, the checkbox kept
      await c.getByRole("button", { name: "Make another" }).click();
      check((await c.locator("audio").count()) === 0 && (await voice.isChecked()), `${tag} Make another: collapsed, the checkbox kept`);
      // the hook only, with a different first line: answered with the hand-written voice (3 lines)
      await narr.getByRole("button", { name: "Hook only" }).click();
      await first.fill("Can you beat it?");
      await c.getByRole("button", { name: "Make the soundtrack" }).click();
      await c.locator("audio").waitFor({ timeout: 15000 });
      const hooked = log.soundtrack[log.soundtrack.length - 1];
      check(
        JSON.stringify(hooked) === JSON.stringify({ creative_id: READY_CID, version: 3, voice: true, voice_name: "Magpie-Multilingual.EN-US.Mia", narration: "hook", line: "Can you beat it?" }),
        `${tag} Hook only + Different first line: ${JSON.stringify(hooked)}`,
      );
      const spoken = await c.getByRole("list", { name: "What is said" }).locator("li").allInnerTexts();
      const wantSpoken = sv.voice.lines.map((l) => `${Math.round(l.at_s * 10) / 10} s · “${l.text}”`);
      check(spoken.length === 3 && JSON.stringify(spoken.map((x) => x.replace(/\s+/g, " ").trim())) === JSON.stringify(wantSpoken), `${tag} the spoken lines: ${spoken.map((x) => x.replace(/\s+/g, " ")).join(" | ")}`);
      check((await c.locator("p", { hasText: sv.description }).count()) === 1 && (await c.locator("audio").getAttribute("src")).endsWith(sv.file), `${tag} the voiced description and file`);
      await cardShot(page, `${label}-soundtrack-edit-voice-${vpName}.png`);
      await c.getByRole("button", { name: "Make another" }).click();
      await voice.uncheck();
      await makeAndCheck(page, tag);
      check(log.real === (realSoundtrack && vpName === "1440" ? 1 : 0), `${tag} ${log.real} real POST /api/soundtrack (voice: false)`);
      if (vpName === "390") {
        const [a, cb] = [await c.locator("audio").boundingBox(), await c.boundingBox()];
        check(a.width >= cb.width - 2 * 20 - 2 * 16 - 2, `${tag} phone: the audio element is full width (${Math.round(a.width)} of ${Math.round(cb.width)})`);
      }
      check((await overflow(page)) === 0, `${tag} no horizontal overflow`);
      await cardShot(page, `${label}-soundtrack-edit-result-${vpName}.png`);
      await page.screenshot({ path: `qa/${label}-edit-soundtrack-${vpName}.png`, fullPage: true, scale: "css" });
      if (vpName === "1440") {
        const seen = new Set();
        await c.getByText("What it follows").click();
        for (let i = 0; i < 3; i++) {
          await page.keyboard.press("Tab");
          seen.add(await page.evaluate(() => (document.activeElement?.textContent || "").trim()));
        }
        check(seen.has("Use as the music") && seen.has("Make another"), `keyboard soundtrack: Tab reaches Use as the music and Make another`);
      }

      // Use as the music → exactly the inventory's music edit, answered here
      await c.getByRole("button", { name: "Use as the music" }).click();
      await c.getByText(/^Used in v4/).waitFor({ timeout: 15000 });
      const d = log.direct[0];
      check(log.direct.length === 1 && JSON.stringify(d) === JSON.stringify({ creative_id: READY_CID, base: 3, op: { music: st.file }, draft: false }), `${tag} Use as the music posts /api/direct ${JSON.stringify(d)}`);
      check((await c.getByRole("link", { name: "Open v4" }).getAttribute("href")) === `/edit?c=${READY_CID}&v=4` && (await c.locator("audio").count()) === 1, `${tag} "Used in v4" with the version link; the card stays`);
      check((await page.getByRole("navigation", { name: "Breadcrumb" }).innerText()).includes("v4"), `${tag} the workspace shows v4 after the edit`);
      check(log.aborted.length === 0, `${tag} no other workflow POST ${log.aborted.join(", ")}`);
      await cardShot(page, `${label}-soundtrack-edit-used-${vpName}.png`);
      noErrors(errors, tag, /status of 502/, page);
      await ctx.close();
    }

    // ── Create page, phase ready ──────────────────────────────────────────────────────────────────
    {
      const tag = `${vpName} soundtrack create:`;
      const { ctx, page, errors } = await featurePage(vp);
      const log = await guard(page);
      await page.addInitScript((j) => localStorage.setItem("cbjStudioJob", JSON.stringify(j)), { id: "qa-ready", kind: "make", page: "create" });
      await page.route("**/api/jobs", (r) => r.fulfill({ json: [{ id: "qa-ready", status: "done" }] }));
      await page.route("**/api/jobs/qa-ready*", (r) => r.fulfill({ json: { id: "qa-ready", kind: "make", status: "done", stage: "done", lines: [], n_lines: 0, result: v3, elapsed: 1 } }));
      await page.goto(base + "/", { waitUntil: "load" });
      const c = card(page);
      const shown = await c.waitFor({ timeout: 15000 }).then(() => true, () => false);
      check(shown && (await page.getByRole("button", { name: "Create another" }).count()) === 1, `${tag} the card on the ready page`);
      const [player, box] = [await page.getByRole("region", { name: "Creative", exact: true }).boundingBox(), await c.boundingBox()];
      check(player && box && box.y > player.y + player.height - 1 && Math.abs(box.x - player.x) < 2, `${tag} under the finished version's player`);
      check(!(await c.getByRole("checkbox", { name: "Narrate the captions" }).isChecked()), `${tag} Narrate the captions off by default`);
      await cardShot(page, `${label}-soundtrack-create-collapsed-${vpName}.png`);
      await makeAndCheck(page, tag);
      check(log.real === 0 && log.soundtrack.length === 1 && log.soundtrack[0].voice === false, `${tag} the fixture answered (no real call here)`);
      check((await overflow(page)) === 0, `${tag} no horizontal overflow`);
      await cardShot(page, `${label}-soundtrack-create-result-${vpName}.png`);
      await page.screenshot({ path: `qa/${label}-create-soundtrack-${vpName}.png`, fullPage: true, scale: "css" });
      await c.getByRole("button", { name: "Use as the music" }).click();
      await c.getByText(/^Used in v4/).waitFor({ timeout: 15000 });
      const d = log.direct[0];
      check(log.direct.length === 1 && JSON.stringify(d) === JSON.stringify({ creative_id: READY_CID, base: 3, op: { music: st.file }, draft: false }), `${tag} Use as the music posts /api/direct ${JSON.stringify(d)}`);
      check((await page.locator("video").first().getAttribute("src"))?.includes(`/${READY_CID}/v4/`) && (await page.getByText("Brief of v4").count()) === 1, `${tag} the page shows the new version (v4)`);
      check(log.aborted.length === 0, `${tag} no other workflow POST ${log.aborted.join(", ")}`);
      await cardShot(page, `${label}-soundtrack-create-used-${vpName}.png`);
      noErrors(errors, tag, undefined, page);
      await ctx.close();
    }
  }

  // ── an engine whose meta says voice: false; an engine without the feature ─────────────────────────
  for (const [what, edit] of [
    ["no voice", (f) => ({ ...f, soundtrack: { bed: true, voice: false } })],
    ["no soundtrack", ({ soundtrack: _drop, ...f }) => (void _drop, f)],
  ]) {
    const { ctx, page, errors } = await featurePage({ width: 1440, height: 900 });
    await guard(page);
    await page.route("**/api/meta", async (r) => {
      const j = await (await r.fetch()).json();
      return r.fulfill({ json: { ...j, features: edit(j.features || {}) } });
    });
    await page.goto(`${base}/edit?c=${READY_CID}&v=3`, { waitUntil: "load" });
    await page.getByText("What changed").first().waitFor({ timeout: 15000 });
    await page.getByText("More: music", { exact: true }).click(); // folded in the designer's Edit workspace
    await page.waitForTimeout(1500);
    if (what === "no voice") {
      const cb = card(page).getByRole("checkbox", { name: "Narrate the captions" });
      check((await cb.isDisabled()) && (await card(page).locator(`span[title="${NO_VOICE_TIP}"]`).filter({ has: page.getByRole("checkbox", { name: "Narrate the captions" }) }).count()) === 1, `meta voice: false: Narrate the captions disabled with "${NO_VOICE_TIP}"`);
      await cardShot(page, `${label}-soundtrack-novoice-1440.png`);
    } else {
      check((await card(page).count()) === 0, "meta without features.soundtrack: no card");
    }
    noErrors(errors, `soundtrack ${what}`, undefined, page);
    await ctx.close();
  }
}
