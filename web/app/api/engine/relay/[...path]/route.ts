import { engineToken, engineUrl, isUnlocked } from "@/lib/session";

export const dynamic = "force-dynamic";

// A same-origin relay to the engine for the calls the browser cannot make directly: reads while the
// session holds no engine token, and every call when the engine sends no CORS headers for this site.
// Only /api/* and /studio/* are relayed; writes need the passcode session. (On Vercel a request body is
// capped at 4.5 MB, so large uploads need the direct path: an engine started with CBJ_CORS_ORIGINS.)

const WRITES = new Set(["plan", "make", "preview", "review", "direct", "upload", "enhance", "trends", "feedback", "lessons", "soundtrack"]);
// Reads that show what designers wrote (names, complaints): the owner's view, behind the passcode like a write.
// A report lists the feedback left on its version, so it is one of them.
const OWNER_READS = new Set(["feedback", "feedback.md", "lessons", "report"]);
// The user's own keys (SPEC-OWN-KEYS §3; engine: src/cbj/keys.py): forwarded on POSTs and on GET api/meta only.
const OWN_KEYS = ["x-cbj-gemini-key", "x-cbj-anthropic-key", "x-cbj-planner"];

const notRelayed = () => Response.json({ detail: "not relayed" }, { status: 404 });

/** The path's segments, cleaned (SPEC-HARDENING §2), or null when one is refused. Next hands the catch-all's segments
 *  over decoded once (".../a%252Fb" arrives as "a%2Fb"), so they are checked as they come and never decoded again: a
 *  segment that still holds a "/", a "\\" or a "%" (an encoded separator, or an encoding of one) or starts with "." (dot
 *  segments, hidden files) is refused, so every check below runs on the exact path that is fetched. */
function clean(parts: string[]): string[] | null {
  if (!parts.length) return null;
  for (const p of parts) if (p === "" || /[/\\%]/.test(p) || p.startsWith(".")) return null;
  return parts;
}

async function relay(request: Request, raw: string[], method: "GET" | "POST") {
  const base = engineUrl();
  if (!base) return Response.json({ detail: "The studio engine is not configured (ENGINE_URL)." }, { status: 503 });
  const parts = clean(raw);
  if (!parts) return Response.json({ detail: "That path is not allowed." }, { status: 400 });
  const [root, second] = parts;
  if (!(root === "api" || root === "studio")) return notRelayed();
  // studio files: only the small JSON ones (videos and pictures load from the engine directly)
  // (the engine refuses its private "_" folders too; the relay never asks for them)
  if (root === "studio" && (!parts[parts.length - 1].endsWith(".json") || parts.slice(1).some((p) => p.startsWith("_")))) {
    return notRelayed();
  }
  if (method === "POST") {
    if (root !== "api" || !WRITES.has(second)) return notRelayed();
    if (!(await isUnlocked())) {
      return Response.json({ detail: "Unlock the studio first: this action runs the engine." }, { status: 401 });
    }
  } else if (root === "api" && OWNER_READS.has(second) && !(await isUnlocked())) {
    return Response.json({ detail: "Unlock the studio first: this page is for the studio's owner." }, { status: 401 });
  }
  const search = new URL(request.url).search;
  const path = `/${parts.map(encodeURIComponent).join("/")}`;
  const href = `${base}${path}${search}`;
  // the URL actually fetched must be the path that was checked (nothing normalised away)
  if (!new URL(href).pathname.endsWith(path)) return notRelayed();
  const headers: Record<string, string> = {};
  if (engineToken()) headers.Authorization = `Bearer ${engineToken()}`;
  const ct = request.headers.get("content-type");
  if (method === "POST" && ct) headers["Content-Type"] = ct;
  if (method === "POST" || (root === "api" && second === "meta" && parts.length === 2)) {
    for (const h of OWN_KEYS) {
      const v = request.headers.get(h);
      if (v) headers[h] = v;
    }
  }
  let r: Response;
  try {
    r = await fetch(href, {
      method,
      headers,
      cache: "no-store",
      // never followed: a redirect would take the token (and the checked path) somewhere else
      redirect: "manual",
      body: method === "POST" ? await request.arrayBuffer() : undefined,
      signal: AbortSignal.timeout(method === "POST" ? 120_000 : 20_000),
    });
  } catch {
    return Response.json({ detail: "The studio engine could not be reached." }, { status: 502 });
  }
  if (r.type === "opaqueredirect" || (r.status >= 300 && r.status < 400)) {
    await r.body?.cancel().catch(() => null);
    return Response.json({ detail: "The studio engine answered with a redirect; it is not followed." }, { status: 502 });
  }
  return new Response(r.body, {
    status: r.status,
    headers: { "Content-Type": r.headers.get("content-type") || "application/json", "Cache-Control": "no-store" },
  });
}

export async function GET(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  return relay(request, (await ctx.params).path, "GET");
}

export async function POST(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  return relay(request, (await ctx.params).path, "POST");
}
