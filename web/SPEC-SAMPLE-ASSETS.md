# SPEC: sample assets on the Create and Edit pages (from the catalogue bucket)

## Why
The test inputs used while building the tool (the Color Block Jam trailers, reference pictures, objects, textures,
logos, stickers, a music track) are published with the catalogue at `<NEXT_PUBLIC_CATALOGUE_URL>/assets/index.json`
(shape: `{note, groups: [{title, items: [{file, path, about, bytes, kind: image|video|audio}]}]}`), so that anyone can
try the same requests. The site should offer them where files are attached.

## What to build (web/ only)
1. **"Sample assets" link** in the *Attachments (optional)* card on Create and in the *Attach the asset the edit uses*
   zone on Edit. Shown only when the catalogue URL is set and `assets/index.json` loads (fetch once per session; silent
   when it fails). It opens a small sheet or popover: the groups with their titles, each item as a row with a thumbnail
   (images: the file itself; videos: a film icon; audio: a note icon), the name, the one-line *about*, the size, and an
   **Attach** button.
2. **Attach** fetches the file from the catalogue (`<base>/<path>`), wraps it as a `File` with its name and type, and
   hands it to the existing attachment path exactly as a dropped file (the same upload to the engine, the same role
   badge, the same limits). A progress state on the button while it downloads; an error line if the fetch fails. Several
   can be attached in a row.
3. **Hint text** under the link: "The files the tool was built and tested with; attach one and describe what to do with
   it." Nothing else on the page changes; without the catalogue URL nothing appears.
4. **QA** (`scripts/qa-sample-assets.mjs`, run from `qa.mjs`, `--sample-assets-only`): route the catalogue host with a
   fixture index of 3 items; check the link appears only with the URL, the sheet lists groups and items, Attach puts
   the file into the attachments list with the right role badge (intercept the upload), the error line on a failed
   fetch, both widths, no console errors.
5. **Docs**: one paragraph in web/README.md's catalogue section.

Constraints: lint and build clean; no file under ../src; do not commit or deploy; a short report at the end.
