import { engineToken, engineUrl } from "@/lib/session";

export const dynamic = "force-dynamic";

// Is the engine up, is it busy, which planner (SPEC §2). Never throws: offline is {online:false}.
// Also reports whether the engine lets this site's origin call it from the browser (CORS); without that,
// the browser goes through /api/engine/relay.

async function probe(url: string, origin: string): Promise<Response | null> {
  try {
    return await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
      headers: { Origin: origin, ...(engineToken() ? { Authorization: `Bearer ${engineToken()}` } : {}) },
    });
  } catch {
    return null;
  }
}

export async function GET(request: Request) {
  const base = engineUrl();
  const origin = new URL(request.url).origin;
  if (!base) return Response.json({ online: false, url: "", reason: "ENGINE_URL is not set" });
  let r = await probe(`${base}/api/health`, origin);
  if (!r || r.status === 404 || r.status === 405) r = await probe(`${base}/api/meta`, origin); // an older engine
  if (!r || !r.ok) return Response.json({ online: false, url: base });
  try {
    const j = (await r.json()) as { busy?: boolean; backend?: string; models?: string[]; effort?: string };
    const allow = r.headers.get("access-control-allow-origin");
    return Response.json({
      online: true,
      busy: Boolean(j.busy),
      backend: j.backend ?? null,
      models: j.models ?? [],
      effort: j.effort ?? null,
      url: base,
      cors: allow === "*" || allow === origin,
    });
  } catch {
    return Response.json({ online: false, url: base });
  }
}
