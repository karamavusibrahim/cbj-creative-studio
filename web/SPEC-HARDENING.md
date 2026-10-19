# SPEC: three hardening points from the security review (web/ only)

1. **The engine token is handed to the browser only behind a passcode** (`app/api/session/route.ts`): when no
   `STUDIO_PASSCODE` is configured, the session answer carries no `engine.token` (the browser then uses the relay for
   everything; direct calls only when CORS allows and no token is needed). With a passcode, keep today's behaviour
   (the token after unlock, so uploads over 4.5 MB go directly). Say so in web/README.md "How it talks to the engine".
2. **The relay normalises before it decides** (`app/api/engine/relay/[...path]/route.ts`): decode each segment once;
   reject (400) any segment that still contains `/`, `\`, `%`, or starts with `.`; build the upstream URL from the
   cleaned segments; run the owner-only check (`OWNER_READS`) and the `/api/*` + `/studio/*.json` allowlist on the
   cleaned path; pass `redirect: "manual"` to the upstream fetch and return 502 on a redirect.
3. **Reports are owner reads** (same file): add `report` to `OWNER_READS`, because a report lists the feedback left
   on a version. The *Download report* button already requires the unlocked session for its call; make sure it uses
   the unlocked path (direct with the token, or the relay after unlock) and shows "Needs the passcode" when locked.

QA: extend the relay checks in `scripts/qa-keys.mjs` (or a small `qa-hardening.mjs`): no token in the session JSON
without a passcode; a path segment with `%2F` or `..` is refused; `/api/report/...` through the relay is 401 when
locked and 200 when unlocked; a redirecting upstream is not followed. Lint and build clean; do not commit or deploy;
a short report at the end.
