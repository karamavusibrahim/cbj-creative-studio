// SPEC-SAMPLE-ASSETS QA, run from qa.mjs (it passes the browser and its check()); `--sample-assets-only` runs just these.
// The build under test must be made with NEXT_PUBLIC_CATALOGUE_URL=https://catalogue.test:
//   NEXT_PUBLIC_CATALOGUE_URL=https://catalogue.test npm run build && npm start -- -p 3105
// https://catalogue.test/* is answered by routing (serveCatalogue): assets/index.json is scripts/fixtures/catalogue/
// assets/index.json (3 items in 2 groups: a PNG logo, an MP4 clip, a WAV tone; their bytes are next to it). Every
// POST /api/upload is answered in the browser (the multipart body is read: the file's name, type and size asserted) and
// every other workflow POST is aborted, so nothing reaches the engine. Checks at 1440 and 390: the link and its hint in
// Create's attachments card and in the Edit workspace's attach zone, the sheet (groups, rows, thumbnails, sizes), Attach
// (the downloading state, the upload as a dropped file, the role badge in the attachments list, the chip on Edit, several
// in a row), the error line on a failed download, nothing shown when the index cannot be read, and, offline, the link
// disabled (label offline, and simulated in an online run). No horizontal overflow; no page errors and no console errors, except the browser's own "Failed to load
// resource" lines for catalogue.test URLs the test makes fail on purpose. Screenshots qa/sample-assets-*.
// A build without the catalogue: only the "off" checks (no link, no hint, nothing asked of any bucket).
import { readFileSync } from "node:fs";
import { CATALOGUE, serveCatalogue } from "./qa-catalogue.mjs";

const INDEX = JSON.parse(readFileSync(new URL("./fixtures/catalogue/assets/index.json", import.meta.url), "utf8"));
const ITEMS = INDEX.groups.flatMap((g) => g.items);
const HINT = "The files the tool was built and tested with; attach one and describe what to do with it.";
const ROLE = { image: "asset to place", video: "reference video, read whole, never placed in the ad", audio: "music for the ad" };
const TYPE = { "asset_a_logo.png": "image/png", "qa_trailer.mp4": "video/mp4", "qa_track.wav": "audio/wav" };
const WORKFLOW = /\/api\/(plan|make|direct|review|preview|enhance|trends|soundtrack|feedback|lessons)(\/|$)/;
const CORS = { "access-control-allow-origin": "*" };
const sizeWord = (n) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

/** The files of a multipart body: [{name, type, size}]. */
function multipart(req) {
  const ct = req.headers()["content-type"] || "";
  const boundary = /boundary=(.+)$/.exec(ct)?.[1];
  const body = req.postDataBuffer();
  if (!boundary || !body) return [];
  const text = body.toString("latin1");
  return text
    .split(`--${boundary}`)
    .filter((part) => part.includes("filename="))
    .map((part) => {
      const head = part.slice(0, part.indexOf("\r\n\r\n"));
      const data = part.slice(part.indexOf("\r\n\r\n") + 4).replace(/\r\n$/, "");
      return { name: /filename="([^"]*)"/.exec(head)?.[1] || "", type: /Content-Type: ([^\r\n]+)/i.exec(head)?.[1] || "", size: Buffer.byteLength(data, "latin1") };
    });
}

export default async function sampleAssetsChecks({ browser, base, label, check, VIEWPORTS, CID, only = false }) {
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const shot = async (page, name) => {
    await page.waitForTimeout(400);
    await page.screenshot({ path: `qa/sample-assets-${name}.png`, fullPage: true, scale: "css" });
  };

  async function open(vp, { index = true, offline = label === "offline" } = {}) {
    const ctx = await browser.newContext({ viewport: vp });
    const log = await serveCatalogue(ctx);
    const page = await ctx.newPage();
    const errors = [];
    const uploads = [];
    const aborted = [];
    const allowed = new Set(); // catalogue.test URLs the test makes fail on purpose
    const asked = []; // every catalogue URL the page asked, routed or not
    page.on("request", (r) => r.url().startsWith(CATALOGUE) && asked.push(r.url().slice(CATALOGUE.length + 1)));
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      const t = m.text();
      if (m.type() !== "error" || /play\(\)|NotAllowedError|AbortError/.test(t)) return;
      const at = m.location()?.url || "";
      if (/^Failed to load resource/.test(t) && [...allowed].some((a) => at.startsWith(a))) return;
      errors.push(`console: ${t} ${at}`);
    });
    await page.route("**/api/**", (r) => {
      const req = r.request();
      const p = new URL(req.url()).pathname;
      if (req.method() === "POST" && p.endsWith("/api/upload")) {
        const files = multipart(req);
        uploads.push(...files);
        return r.fulfill({ headers: CORS, json: { uploaded: files.map((f) => f.name) } });
      }
      if (req.method() === "POST" && WORKFLOW.test(p)) {
        aborted.push(p);
        return r.abort();
      }
      return r.fallback();
    });
    // offline (also simulated in an online run); online, the studio engine may be busy with someone else's job: answered
    // as idle, so the attach zones stay enabled
    if (offline) await page.route("**/api/engine/health", (r) => r.fulfill({ json: { online: false, url: "" } }));
    else await page.route("**/api/engine/health", async (r) => r.fulfill({ json: { ...(await (await r.fetch()).json()), busy: false } }));
    if (!index) {
      allowed.add(`${CATALOGUE}/assets/index.json`);
      await page.route(`${CATALOGUE}/assets/index.json`, (r) => r.fulfill({ status: 404, headers: { ...CORS, "content-type": "application/xml" }, body: "<Error><Code>NoSuchKey</Code></Error>" }));
    }
    return { ctx, page, errors, uploads, aborted, allowed, log, asked };
  }
  const link = (scope) => scope.getByRole("button", { name: "Sample assets" });
  const sheet = (page) => page.getByRole("dialog", { name: "Sample assets" });
  const attachBtn = (scope, file) => scope.getByRole("button", { name: new RegExp(`^(Attach|Downloading…|Attaching…|Attached|Try again) ${file.replace(".", "\\.")}$`) });
  const createCard = (page) => page.getByRole("region", { name: "Attachments (optional)" });
  async function gotoCreate(page, offline = label === "offline") {
    await page.goto(`${base}/`, { waitUntil: "load" });
    await page.getByText("Create a new creative").first().waitFor({ timeout: 15000 });
    if (offline) await page.getByText("Engine offline").first().waitFor({ state: "attached", timeout: 15000 });
    else await page.locator('[role="status"]').filter({ hasText: "Online" }).first().waitFor({ timeout: 15000 });
  }
  async function offlineChecks(vpName, vp) {
    const { ctx, page, errors } = await open(vp, { offline: true });
    await gotoCreate(page, true);
    await link(createCard(page)).waitFor({ timeout: 10000 }).catch(() => null);
    check((await link(createCard(page)).count()) === 1 && (await link(createCard(page)).isDisabled()), `${vpName} sample assets offline: the link is shown, disabled (attaching needs the engine)`);
    check((await createCard(page).getByText(HINT).count()) === 1, `${vpName} sample assets offline: the hint`);
    check((await overflow(page)) === 0, `${vpName} sample assets offline: no horizontal overflow`);
    check(errors.length === 0, `${vpName} sample assets offline: no page/console errors ${errors.join("; ")}`);
    await ctx.close();
  }
  async function gotoEdit(page) {
    await page.goto(`${base}/edit?c=${CID}&v=13`, { waitUntil: "load" });
    await page.getByText("Attach the asset the edit uses").first().waitFor({ timeout: 15000 });
  }

  // is this build's catalogue on? (one Create page load: a request for assets/index.json, or none)
  {
    const { ctx, page, log, errors } = await open(VIEWPORTS[0][1]);
    await gotoCreate(page);
    await page.waitForTimeout(1500);
    const on = log.asked.includes("assets/index.json");
    if (!on) {
      check((await link(page).count()) === 0 && (await page.getByText(HINT).count()) === 0, "sample assets off: no link, no hint on Create");
      await gotoEdit(page);
      await page.waitForTimeout(1200);
      check((await link(page).count()) === 0 && (await page.getByText(HINT).count()) === 0, "sample assets off: no link, no hint on Edit");
      check(!log.asked.some((p) => p.startsWith("assets/")), "sample assets off: nothing asked of the bucket");
      check(errors.length === 0, `sample assets off: no page/console errors ${errors.join("; ")}`);
      check(!only, `sample assets: this build has no NEXT_PUBLIC_CATALOGUE_URL=${CATALOGUE} (build it with that to run the sample-asset checks)`);
      await ctx.close();
      return;
    }
    await ctx.close();
  }

  if (label === "offline") {
    for (const [vpName, vp] of VIEWPORTS) await offlineChecks(vpName, vp);
    return;
  }

  for (const [vpName, vp] of VIEWPORTS) {
    const tag = `${vpName} sample assets:`;

    // ── Create: the link, the sheet, Attach ×3 in a row, the attachments list ─────────────────────────────
    {
      const { ctx, page, errors, uploads, aborted, log } = await open(vp);
      // slow downloads, so the button's progress state can be seen
      await page.route(`${CATALOGUE}/assets/**`, async (r) => {
        if (!r.request().url().endsWith("/index.json")) await new Promise((ok) => setTimeout(ok, 700));
        return r.fallback();
      });
      await gotoCreate(page);
      const card = createCard(page);
      await link(card).waitFor({ timeout: 10000 });
      check((await link(card).count()) === 1 && !(await link(card).isDisabled()), `${tag} Create: the link in the Attachments (optional) card`);
      check((await card.getByText(HINT, { exact: true }).count()) === 1, `${tag} Create: the hint under it`);
      check((await link(page).count()) === 1, `${tag} Create: one link on the page`);

      await link(card).click();
      const dlg = sheet(page);
      await dlg.waitFor({ timeout: 5000 });
      const heads = await dlg.getByRole("heading", { level: 3 }).allInnerTexts();
      check(JSON.stringify(heads) === JSON.stringify(INDEX.groups.map((g) => g.title)), `${tag} sheet: the groups with their titles (${heads.join(" | ")})`);
      check((await dlg.getByText(INDEX.note).count()) === 1, `${tag} sheet: the index's note`);
      const rows = dlg.locator("li");
      check((await rows.count()) === ITEMS.length, `${tag} sheet: ${ITEMS.length} rows (${await rows.count()})`);
      for (const it of ITEMS) {
        const row = rows.filter({ hasText: it.file });
        const text = (await row.innerText()).replace(/\s+/g, " ");
        const img = row.locator("img");
        const thumb =
          it.kind === "image"
            ? (await img.count()) === 1 && (await img.getAttribute("src")) === `${CATALOGUE}/${it.path}`
            : (await img.count()) === 0 && (await row.locator("svg").count()) >= 1;
        check(
          text.includes(it.about) && text.includes(sizeWord(it.bytes)) && thumb && (await attachBtn(row, it.file).innerText()).trim() === "Attach",
          `${tag} sheet: ${it.file}: name, about, ${sizeWord(it.bytes)}, ${it.kind === "image" ? "the picture itself" : "an icon"} as thumbnail, Attach`,
        );
      }
      await page.waitForFunction(() => [...document.querySelectorAll("dialog img")].every((i) => i.complete && i.naturalWidth > 0), null, { timeout: 5000 }).catch(() => null);
      check(await dlg.locator("img").first().evaluate((i) => i.naturalWidth > 0), `${tag} sheet: the image thumbnail loaded from the bucket`);
      check((await overflow(page)) === 0, `${tag} sheet: no horizontal overflow`);
      await shot(page, `sheet-${vpName}`);

      // Attach the picture: Downloading… while it downloads, then Attached
      const [logo, clip, tone] = ITEMS;
      await attachBtn(dlg, logo.file).click();
      await page.waitForTimeout(200);
      const during = attachBtn(dlg, logo.file);
      check(
        (await during.innerText()).trim() === "Downloading…" && (await during.isDisabled()) && (await during.getAttribute("aria-busy")) === "true",
        `${tag} Attach: "Downloading…" (disabled, busy) while it downloads`,
      );
      await dlg.getByRole("button", { name: `Attached ${logo.file}` }).waitFor({ timeout: 10000 });
      // then two more in a row, without waiting between them
      await attachBtn(dlg, clip.file).click();
      await attachBtn(dlg, tone.file).click();
      await dlg.getByRole("button", { name: `Attached ${clip.file}` }).waitFor({ timeout: 10000 });
      await dlg.getByRole("button", { name: `Attached ${tone.file}` }).waitFor({ timeout: 10000 });
      check(true, `${tag} Attach: all three attached, two of them in a row`);
      const got = uploads.map((u) => `${u.name}:${u.type}:${u.size}`).sort();
      const want = ITEMS.map((i) => `${i.file}:${TYPE[i.file]}:${i.bytes}`).sort();
      check(JSON.stringify(got) === JSON.stringify(want), `${tag} Attach: POST /api/upload got each file with its name, type and size (${got.join(", ")})`);
      check((await dlg.getByRole("alert").count()) === 0, `${tag} Attach: no error line`);

      await page.keyboard.press("Escape");
      await dlg.waitFor({ state: "hidden", timeout: 5000 });
      check(await link(card).evaluate((el) => el === document.activeElement), `${tag} sheet: Escape closes it and focus returns to the link`);
      const list = card.locator("ul > li");
      check((await list.count()) === ITEMS.length, `${tag} Create: ${ITEMS.length} files in the attachments list (${await list.count()})`);
      for (const it of ITEMS) {
        const row = list.filter({ hasText: it.file });
        const text = (await row.innerText().catch(() => "")).replace(/\s+/g, " ");
        check(text.includes(ROLE[it.kind]), `${tag} Create: ${it.file} with its role badge "${ROLE[it.kind]}"`);
      }
      const local = await list.filter({ hasText: logo.file }).locator("img").getAttribute("src");
      check(Boolean(local?.startsWith("blob:")), `${tag} Create: the picture's thumbnail is its own bytes, as for a dropped file (${local?.slice(0, 12)}…)`);
      check((await card.getByText("3 files").count()) === 1, `${tag} Create: the card's count says 3 files`);

      // the prompt decides an image's role, exactly as for a dropped file
      await page.fill("#prompt", "Use this picture's colours for the board.");
      await page.waitForTimeout(300);
      const imgRole = (await list.filter({ hasText: logo.file }).innerText()).replace(/\s+/g, " ");
      check(imgRole.includes("reference image"), `${tag} Create: with reference words the picture becomes "reference image"`);

      await link(card).click();
      await dlg.waitFor({ timeout: 5000 });
      check((await attachBtn(dlg, logo.file).innerText()).trim() === "Attach", `${tag} sheet: reopened fresh`);
      await page.keyboard.press("Escape");
      check(log.asked.filter((p) => p === "assets/index.json").length === 1, `${tag} index.json asked once`);
      check(aborted.length === 0, `${tag} Create: no workflow POST (${aborted.join(", ")})`);
      check((await overflow(page)) === 0, `${tag} Create: no horizontal overflow`);
      await card.scrollIntoViewIfNeeded();
      await shot(page, `create-${vpName}`);
      check(errors.length === 0, `${tag} Create: no page/console errors ${errors.join("; ")}`);
      await ctx.close();
    }

    // ── a failed download: the error line, no upload, the others still attach ────────────────────────────
    {
      const { ctx, page, errors, uploads, allowed } = await open(vp);
      const clip = ITEMS.find((i) => i.kind === "video");
      const logo = ITEMS.find((i) => i.kind === "image");
      allowed.add(`${CATALOGUE}/${clip.path}`);
      await page.route(`${CATALOGUE}/${clip.path}`, (r) => r.fulfill({ status: 404, headers: { ...CORS, "content-type": "application/xml" }, body: "<Error><Code>NoSuchKey</Code></Error>" }));
      await gotoCreate(page);
      await link(createCard(page)).click();
      const dlg = sheet(page);
      await dlg.waitFor({ timeout: 5000 });
      await attachBtn(dlg, clip.file).click();
      const alert = dlg.locator("li").filter({ hasText: clip.file }).getByRole("alert");
      await alert.waitFor({ timeout: 10000 }).catch(() => null);
      const msg = (await alert.innerText().catch(() => "")).trim();
      check(msg === `${clip.file} could not be downloaded from the catalogue (HTTP 404).`, `${tag} failed download: the error line "${msg}"`);
      check((await attachBtn(dlg, clip.file).innerText()).trim() === "Try again" && !(await attachBtn(dlg, clip.file).isDisabled()), `${tag} failed download: the button offers Try again`);
      check(uploads.length === 0, `${tag} failed download: nothing uploaded`);
      await attachBtn(dlg, logo.file).click();
      await dlg.getByRole("button", { name: `Attached ${logo.file}` }).waitFor({ timeout: 10000 });
      check(uploads.length === 1 && uploads[0].name === logo.file, `${tag} failed download: another one still attaches`);
      check((await overflow(page)) === 0, `${tag} failed download: no horizontal overflow`);
      await shot(page, `error-${vpName}`);
      await page.keyboard.press("Escape");
      check((await createCard(page).locator("ul > li").count()) === 1, `${tag} failed download: only the attached one is in the list`);
      check(errors.length === 0, `${tag} failed download: no page/console errors ${errors.join("; ")}`);
      await ctx.close();
    }

    // ── Edit: the link in the attach zone, Attach → the chip ─────────────────────────────────────────────
    {
      const { ctx, page, errors, uploads, aborted } = await open(vp);
      await gotoEdit(page);
      await link(page).waitFor({ timeout: 10000 });
      const zone = page.getByText("Attach the asset the edit uses").locator("xpath=ancestor::div[@role='button'][1]/..");
      check((await link(zone).count()) === 1 && !(await link(zone).isDisabled()) && (await zone.getByText(HINT, { exact: true }).count()) === 1, `${tag} Edit: the link and its hint under the attach zone`);
      await link(zone).click();
      const dlg = sheet(page);
      await dlg.waitFor({ timeout: 5000 });
      check((await dlg.locator("li").count()) === ITEMS.length, `${tag} Edit: the sheet lists ${ITEMS.length} items`);
      const tone = ITEMS.find((i) => i.kind === "audio");
      const logo = ITEMS.find((i) => i.kind === "image");
      await attachBtn(dlg, tone.file).click();
      await attachBtn(dlg, logo.file).click();
      await dlg.getByRole("button", { name: `Attached ${tone.file}` }).waitFor({ timeout: 10000 });
      await dlg.getByRole("button", { name: `Attached ${logo.file}` }).waitFor({ timeout: 10000 });
      await page.keyboard.press("Escape");
      await dlg.waitFor({ state: "hidden", timeout: 5000 });
      check(
        (await zone.getByRole("button", { name: `Remove ${tone.file}` }).count()) === 1 && (await zone.getByRole("button", { name: `Remove ${logo.file}` }).count()) === 1,
        `${tag} Edit: both files are chips of the request, as dropped files are`,
      );
      check(
        uploads.length === 2 && uploads.some((u) => u.name === tone.file && u.type === "audio/wav" && u.size === tone.bytes),
        `${tag} Edit: POST /api/upload got the files (${uploads.map((u) => `${u.name}:${u.type}:${u.size}`).join(", ")})`,
      );
      check(aborted.length === 0, `${tag} Edit: no workflow POST (${aborted.join(", ")})`);
      check((await overflow(page)) === 0, `${tag} Edit: no horizontal overflow`);
      await zone.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `qa/sample-assets-edit-${vpName}.png`, scale: "css" });
      check(errors.length === 0, `${tag} Edit: no page/console errors ${errors.join("; ")}`);
      await ctx.close();
    }

    // ── the engine offline (simulated): the link is there, disabled ─────────────────────────────────────
    await offlineChecks(vpName, vp);

    // ── the index cannot be read: nothing appears, silently ──────────────────────────────────────────────
    {
      const { ctx, page, errors, asked } = await open(vp, { index: false });
      await gotoCreate(page);
      await page.waitForTimeout(1500);
      check(asked.includes("assets/index.json"), `${tag} no index: the index was asked (answered 404)`);
      check((await link(page).count()) === 0 && (await page.getByText(HINT).count()) === 0, `${tag} no index: no link, no hint on Create`);
      await gotoEdit(page);
      await page.waitForTimeout(1200);
      check((await link(page).count()) === 0 && (await page.getByText(HINT).count()) === 0, `${tag} no index: no link, no hint on Edit`);
      check(errors.length === 0, `${tag} no index: no page/console errors ${errors.join("; ")}`);
      await ctx.close();
    }
  }
}
