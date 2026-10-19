// SPEC-R2-CATALOGUE QA, run from qa.mjs (it passes the browser and its check()); `--catalogue-only` runs just these.
// The build under test must be made with NEXT_PUBLIC_CATALOGUE_URL=https://catalogue.test:
//   NEXT_PUBLIC_CATALOGUE_URL=https://catalogue.test npm run build && npm start -- -p 3105
// https://catalogue.test/* is answered here by Playwright routing (`.test` never resolves, so nothing leaves the
// machine): index.json and one <id>/showcase.json from scripts/fixtures/catalogue/ (3 creatives: one also curated,
// with a different title that must never show; one with its showcase.json and an edit version; one listed without
// one, whose page is the 404 state); the media a fixture names are the bytes of public/showcase/ (the exported layout).
// Checks at 1440 and 390: the ten first and unchanged, the appended items with the "catalogue" badge, the heading's
// count, the filters (Edits included), a catalogue detail page with every medium and file link on the catalogue host,
// "Open in the Edit workspace" only when the engine holds the creative, the 404 state, and an unreachable catalogue
// (no route: the name does not resolve) leaving the static showcase intact. No horizontal overflow; no page errors and
// no console errors, except the browser's own "Failed to load resource" lines for catalogue.test URLs the test makes
// fail on purpose (those come from the network layer, not from the app). Screenshots qa/catalogue-*.
// A build without the catalogue: only the "off" checks (the line says "10 curated", nothing is asked of any bucket).
import { existsSync, readFileSync } from "node:fs";
import { extname } from "node:path";
import { engineJson } from "./qa-engine.mjs";

export const CATALOGUE = "https://catalogue.test";
const FIX = new URL("./fixtures/catalogue/", import.meta.url);
const STATIC = new URL("../public/showcase/", import.meta.url);
const TYPES = { ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".mp4": "video/mp4", ".wav": "audio/wav", ".webp": "image/webp" };
const DETAIL_ID = "1017-232148-a-cross-shaped-board-8x8";
const MISSING_ID = "1020-101500-qa-catalogue-video-only";

/** Serve the fixture bucket on a context (also used by qa.mjs for its other pages, so a catalogue build never logs a
 *  failed request there). Returns the log of what was asked. */
export async function serveCatalogue(ctx, log = { asked: [], missing: [] }) {
  await ctx.route(`${CATALOGUE}/**`, async (r) => {
    const p = decodeURIComponent(new URL(r.request().url()).pathname.replace(/^\/+/, ""));
    log.asked.push(p);
    const cors = { "access-control-allow-origin": "*" };
    if (p.includes("..")) return r.fulfill({ status: 400, headers: cors, body: "" });
    const fixture = new URL(p, FIX);
    const file = existsSync(fixture) ? fixture : p.endsWith("showcase.json") || p === "index.json" ? null : new URL(p, STATIC);
    if (!file || !existsSync(file)) {
      log.missing.push(p);
      return r.fulfill({ status: 404, headers: { ...cors, "content-type": "application/xml" }, body: "<Error><Code>NoSuchKey</Code></Error>" });
    }
    return r.fulfill({ status: 200, headers: { ...cors, "content-type": TYPES[extname(p)] || "application/octet-stream" }, body: readFileSync(file) });
  });
  return log;
}

export default async function catalogueChecks({ browser, base, check, VIEWPORTS, only = false }) {
  const curated = JSON.parse(readFileSync(new URL("index.json", STATIC), "utf8")).creatives;
  const cat = JSON.parse(readFileSync(new URL("index.json", FIX), "utf8")).creatives;
  const extra = cat.filter((c) => !curated.some((s) => s.id === c.id));
  const all = [...curated, ...extra];
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const shot = async (page, name) => {
    await page.waitForTimeout(500);
    await page.screenshot({ path: `qa/catalogue-${name}.png`, fullPage: true, scale: "css" });
  };
  const KINDS = {
    All: () => true,
    Text: (c) => c.kind === "create",
    "Image reference": (c) => c.kind === "image_guided",
    "Video reference": (c) => c.kind === "guided",
    Edits: (c) => c.kind === "edit" || c.kind === "edit-ladder" || c.versions.some((v) => v.edit),
  };
  let held = false;
  try {
    held = (await engineJson(`/api/creatives/${DETAIL_ID}`)).length > 0;
  } catch {
    held = false; // offline, or the engine does not hold it
  }

  async function open(vp, { bucket = true } = {}) {
    const ctx = await browser.newContext({ viewport: vp });
    const page = await ctx.newPage();
    const errors = [];
    const warnings = [];
    const log = bucket ? await serveCatalogue(ctx) : { asked: [], missing: [] };
    const allowed = new Set(); // catalogue.test URLs the test makes fail on purpose
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      const t = m.text();
      if (m.type() === "warning" && /catalogue/i.test(t)) warnings.push(t);
      if (m.type() !== "error" || /play\(\)|NotAllowedError|AbortError/.test(t)) return;
      const at = m.location()?.url || "";
      if (/^Failed to load resource/.test(t) && at.startsWith(CATALOGUE) && [...allowed].some((a) => at.startsWith(a))) return;
      errors.push(`console: ${t} ${at}`);
    });
    if (!bucket) {
      // nothing routed: let the browser fail on its own (the name does not resolve); the failure line is the network's
      page.on("requestfailed", (r) => r.url().startsWith(CATALOGUE) && log.asked.push(r.url()));
      allowed.add(CATALOGUE);
    }
    return { ctx, page, errors, warnings, log, allowed };
  }
  const cards = (page) => page.locator("main ul > li a[href^='/showcase/']");
  const line = (page) => page.locator("h1 ~ p[aria-live]").first();

  // is this build's catalogue on? (one page load: a request to the bucket, or none)
  {
    const { ctx, page, log } = await open(VIEWPORTS[0][1]);
    await page.goto(`${base}/showcase`, { waitUntil: "load" });
    await page.waitForTimeout(1500);
    const on = log.asked.includes("index.json");
    await ctx.close();
    if (!on) {
      for (const [vpName, vp] of VIEWPORTS) {
        const { ctx: c2, page: p2, errors } = await open(vp);
        await p2.goto(`${base}/showcase`, { waitUntil: "load" });
        await p2.waitForTimeout(1200);
        const text = ((await line(p2).textContent()) || "").trim();
        check(text === `${curated.length} curated` && (await cards(p2).count()) === curated.length, `${vpName} catalogue off: the line says "${text}", ${await cards(p2).count()} cards`);
        check(errors.length === 0, `${vpName} catalogue off: no page/console errors ${errors.join("; ")}`);
        await c2.close();
      }
      check(!only, `catalogue: this build has no NEXT_PUBLIC_CATALOGUE_URL=${CATALOGUE} (build it with that to run the catalogue checks)`);
      return;
    }
  }

  for (const [vpName, vp] of VIEWPORTS) {
    const tag = `${vpName} catalogue:`;

    // ── the gallery: the ten first and unchanged, then the catalogue's others ─────────────────────────
    {
      const { ctx, page, errors, log } = await open(vp);
      await page.goto(`${base}/showcase`, { waitUntil: "load" });
      await page.getByText("Finished creatives").first().waitFor({ timeout: 15000 });
      await page.waitForFunction((n) => document.querySelectorAll("main ul > li a[href^='/showcase/']").length >= n, all.length, { timeout: 10000 }).catch(() => null);
      const got = await cards(page).evaluateAll((as) =>
        as.map((a) => ({ href: a.getAttribute("href"), title: a.querySelector(".text-title-sm")?.textContent?.trim() || "", badge: /catalogue/.test(a.textContent || ""), poster: a.querySelector("img")?.getAttribute("src") || "" })),
      );
      const head = got.slice(0, curated.length);
      check(
        head.length === curated.length && head.every((g, i) => g.href === `/showcase/${curated[i].id}` && g.title === curated[i].title && !g.badge && g.poster.startsWith("/showcase/")),
        `${tag} the ${curated.length} curated first, in order, with their own titles and posters, no badge`,
      );
      check(!got.some((g) => g.title.startsWith("CATALOGUE COPY")), `${tag} the curated creative also in the catalogue shows its static copy`);
      const tail = got.slice(curated.length);
      check(
        tail.length === extra.length && tail.every((g, i) => g.href === `/showcase/${extra[i].id}` && g.title === extra[i].title && g.badge && g.poster.startsWith(`${CATALOGUE}/`)),
        `${tag} then ${extra.length} from the catalogue in its order, badged "catalogue", posters on ${CATALOGUE} (${tail.map((g) => g.href).join(", ")})`,
      );
      const text = ((await line(page).textContent()) || "").trim();
      check(text === `${curated.length} curated · ${extra.length} more in the catalogue`, `${tag} the heading's line: "${text}"`);
      check(log.asked.filter((p) => p === "index.json").length === 1, `${tag} index.json asked once`);
      for (const [name, f] of Object.entries(KINDS)) {
        const btn = page.getByRole("group", { name: "Filter by kind" }).getByRole("button", { name: new RegExp(`^${name}`) });
        await btn.click();
        await page.waitForTimeout(250);
        const want = all.filter(f).map((c) => `/showcase/${c.id}`);
        const seen = await cards(page).evaluateAll((as) => as.map((a) => a.getAttribute("href")));
        const n = Number(((await btn.textContent()) || "").replace(/\D+/g, ""));
        check(JSON.stringify(seen) === JSON.stringify(want) && n === want.length, `${tag} filter ${name}: ${seen.length} cards (count ${n}, want ${want.length})`);
        if (name === "Edits") check(seen.includes(`/showcase/${DETAIL_ID}`), `${tag} the Edits filter includes the edited catalogue creative`);
      }
      await page.getByRole("group", { name: "Filter by kind" }).getByRole("button", { name: /^All/ }).click();
      check((await overflow(page)) === 0, `${tag} gallery: no horizontal overflow`);
      check(log.missing.length === 0, `${tag} gallery: nothing missing on the bucket ${log.missing.join(", ")}`);
      await shot(page, `gallery-${vpName}`);
      check(errors.length === 0, `${tag} gallery: no page/console errors ${errors.join("; ")}`);

      // ── a catalogue creative's page, reached from its card ─────────────────────────────────────────
      await cards(page).filter({ hasText: extra.find((c) => c.id === DETAIL_ID).title }).click();
      await page.waitForURL(`**/showcase/${DETAIL_ID}`);
      const detail = JSON.parse(readFileSync(new URL(`${DETAIL_ID}/showcase.json`, FIX), "utf8"));
      await page.getByRole("heading", { level: 1, name: detail.title }).waitFor({ timeout: 15000 });
      await page.waitForTimeout(2000);
      check((await page.getByText("Catalogue · exported from the studio").count()) === 1, `${tag} detail: the catalogue's page ("Catalogue · exported from the studio")`);
      const media = await page.evaluate(() =>
        [...document.querySelectorAll("video[src], video[poster], source[src], img[src]")]
          .flatMap((el) => [el.getAttribute("src"), el.getAttribute("poster")])
          .filter((s) => s && !s.startsWith("data:") && !s.startsWith("/icon")),
      );
      check(media.length > 0 && media.every((s) => s.startsWith(`${CATALOGUE}/`)), `${tag} detail: every medium on the catalogue host (${media.length}: ${media.find((s) => !s.startsWith(CATALOGUE)) || media[0]})`);
      const vid = await page.locator("video").first().getAttribute("src");
      check(vid === `${CATALOGUE}/${detail.versions.at(-1).video}`, `${tag} detail: the player plays ${vid}`);
      const links = await page.evaluate(() => [...document.querySelectorAll("a[target=_blank][href]")].map((a) => a.getAttribute("href")));
      check(links.length > 0 && links.every((h) => h.startsWith(`${CATALOGUE}/`)), `${tag} detail: file links on the catalogue host (${links.length})`);
      const editLink = await page.getByRole("link", { name: "Open in the Edit workspace" }).count();
      check(editLink === (held ? 1 : 0), `${tag} detail: "Open in the Edit workspace" ${held ? "shown (the engine holds it)" : "hidden (the engine does not hold it)"}`);
      if (detail.versions.length > 1) {
        const first = detail.versions[0].n;
        await page.getByRole("tab", { name: new RegExp(`^v${first}\\b`) }).click();
        await page.waitForTimeout(800);
        const v1 = await page.locator("video").first().getAttribute("src");
        check(v1 === `${CATALOGUE}/${detail.versions[0].video}`, `${tag} detail: v${first} also plays from the bucket`);
      }
      check(log.missing.length === 0, `${tag} detail: every file it asked is on the bucket ${log.missing.join(", ")}`);
      check((await overflow(page)) === 0, `${tag} detail: no horizontal overflow`);
      await shot(page, `detail-${vpName}`);
      check(errors.length === 0, `${tag} detail: no page/console errors ${errors.join("; ")}`);

      // ── a curated creative's page stays the static one ─────────────────────────────────────────────
      await page.goto(`${base}/showcase/${curated[0].id}`, { waitUntil: "load" });
      await page.getByRole("heading", { level: 1, name: curated[0].title }).waitFor({ timeout: 15000 });
      await page.waitForTimeout(800);
      const vs = await page.locator("video").first().getAttribute("src");
      check((await page.getByText("Showcase · exported from the studio").count()) === 1 && vs?.startsWith("/showcase/"), `${tag} a curated page is unchanged (static media: ${vs})`);
      await ctx.close();
    }

    // ── the 404 state ───────────────────────────────────────────────────────────────────────────────
    {
      const { ctx, page, errors, allowed } = await open(vp);
      allowed.add(`${CATALOGUE}/${MISSING_ID}/showcase.json`);
      await page.goto(`${base}/showcase/${MISSING_ID}`, { waitUntil: "load" });
      const loading = await page.getByText("Loading from the catalogue…").count();
      await page.getByRole("heading", { level: 1, name: "Not in the catalogue" }).waitFor({ timeout: 15000 });
      check(true, `${tag} 404: "Not in the catalogue" (loading state seen: ${loading ? "yes" : "too quick"})`);
      check((await page.getByRole("link", { name: "All finished creatives" }).count()) === 1, `${tag} 404: a way back to the gallery`);
      check((await overflow(page)) === 0, `${tag} 404: no horizontal overflow`);
      await shot(page, `404-${vpName}`);
      check(errors.length === 0, `${tag} 404: no page/console errors ${errors.join("; ")}`);
      await ctx.close();
    }

    // ── unreachable: the static showcase alone, intact ────────────────────────────────────────────────
    {
      const { ctx, page, errors, warnings, log } = await open(vp, { bucket: false });
      await page.goto(`${base}/showcase`, { waitUntil: "load" });
      await page.getByText("Finished creatives").first().waitFor({ timeout: 15000 });
      await page.waitForFunction(() => !/loading the catalogue/.test(document.querySelector("h1 ~ p[aria-live]")?.textContent || ""), null, { timeout: 15000 }).catch(() => null);
      await page.waitForTimeout(500);
      const got = await cards(page).evaluateAll((as) => as.map((a) => a.getAttribute("href")));
      const text = ((await line(page).textContent()) || "").trim();
      check(JSON.stringify(got) === JSON.stringify(curated.map((c) => `/showcase/${c.id}`)), `${tag} unreachable: the ${curated.length} curated, in order, nothing else (${got.length})`);
      check(text === `${curated.length} curated`, `${tag} unreachable: the line says only "${text}"`);
      check(log.asked.length >= 1 && warnings.length === 1, `${tag} unreachable: the bucket was asked and the failure logged once, as a warning (${warnings.length})`);
      check((await overflow(page)) === 0, `${tag} unreachable: no horizontal overflow`);
      await shot(page, `unreachable-${vpName}`);
      check(errors.length === 0, `${tag} unreachable: no page/console errors ${errors.join("; ")}`);
      await ctx.close();
    }
  }
}
