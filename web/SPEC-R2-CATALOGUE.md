# SPEC: the catalogue — more finished creatives from Cloudflare R2, with the Mac off

## Why
The static showcase (10 curated creatives in `public/showcase/`) is what reviewers see when the engine is offline.
The owner wants more finished creatives visible over time without redeploying and without the Mac: a catalogue of
about 100 creatives (the ten curated first, every kind of the case present) is exported by
`scripts/r2_publish.py` to a public Cloudflare R2 bucket in exactly the static showcase's layout
(`index.json`, `<id>/showcase.json`, `<id>/v<n>/ad/ad.mp4` at 720p, posters, boards, `brief.json`, `level.json`,
`review.json` and its sheet, `inventory.json`, `uploads/…`, `sprites/…`). The bucket's public base URL comes in
`NEXT_PUBLIC_CATALOGUE_URL` (no trailing slash). CORS on the bucket allows GET from any origin.

## What to build (web/ only)
1. **A catalogue source** (`lib/catalogue.ts`): when `NEXT_PUBLIC_CATALOGUE_URL` is set, fetch `<base>/index.json`
   client-side (cache in memory for the session; `cache: "no-store"` on the request), tolerate failure (log once,
   return []). Items have the same shape as the static `index.json`. A creative that is also in the static showcase is
   taken from the static copy (the ten curated stay first and unchanged); the rest follow in the catalogue's order.
2. **The Showcase gallery** (`/showcase`): renders the static items at once (as today), then appends the catalogue
   items when they arrive. The heading's line says "10 curated · N more in the catalogue" (or only the first part when
   the catalogue is off or unreachable). Filters and kind labels as today; the Edits filter still uses
   `versions.some(v => v.edit)` so edited catalogue creatives show there too. A small badge "catalogue" on those cards.
3. **The detail page** (`/showcase/[id]`): static for the ten as today. For any other id, render client-side from
   `<base>/<id>/showcase.json` (the same component as today fed with that data; a short loading state; a plain
   "Not in the catalogue" state on 404). Media and file links for a catalogue creative resolve to `<base>/<path>`
   (today the resolver chooses `<engine>/studio/<path>` online or `/showcase/<path>` offline — add the third source
   and choose it whenever the creative came from the catalogue, even when the engine is online, because the engine
   may not hold that creative any more). "Open in the Edit workspace" only when the engine is online AND holds it
   (one GET, as the feedback panel already does). The feedback panel's rule is unchanged.
4. **Next config**: the catalogue host must be allowed for `<video>`/`<img>` (no `next/image` optimisation on it).
5. **Nothing else changes**: Create, Edit, the engine client, the relay and the static export stay as they are.

## QA (`scripts/qa-catalogue.mjs`, run from `qa.mjs`, with `--catalogue-only`)
Route `https://catalogue.test/*` with fixtures (an `index.json` of 3 creatives, one of which is also curated, and one
`showcase.json`), set `NEXT_PUBLIC_CATALOGUE_URL=https://catalogue.test` for the production build under test. Check:
the ten first and unchanged, the appended items with the badge, the heading count, the filters, a catalogue detail
page with media on the catalogue host, the 404 state, and that an unreachable catalogue leaves the static showcase
intact with no console error. Both widths, no overflow.

## Docs
`web/README.md`: a section "The catalogue on Cloudflare R2" (the env var, how it is published with
`uv run python scripts/r2_publish.py export && … upload`, and that the ten curated stay first). The root README's
website section gets one sentence pointing there.

Constraints: `npm run lint` and `npm run build` clean; do not commit; do not deploy; end with a short report.
