import { cookies } from "next/headers";
import { COOKIE, engineToken, engineUrl, isUnlocked, passcodeRequired, same, sessionValue } from "@/lib/session";

export const dynamic = "force-dynamic";

// The engine token reaches the browser only behind a passcode (SPEC-HARDENING §1): after unlocking, so uploads over the
// relay's 4.5 MB cap go directly. Without a passcode anyone could read it here, so the answer carries none, and the
// browser calls the engine directly only when it needs no token (`direct`); everything else goes through the relay.
export async function GET() {
  const unlocked = await isUnlocked();
  const required = passcodeRequired();
  if (!unlocked) return Response.json({ unlocked: false, required });
  const engine = required ? { url: engineUrl(), token: engineToken(), direct: true } : { url: engineUrl(), direct: !engineToken() };
  return Response.json({ unlocked: true, required, engine });
}

export async function POST(request: Request) {
  const code = process.env.STUDIO_PASSCODE;
  if (!code) return Response.json({ unlocked: true, required: false });
  let passcode = "";
  try {
    const body = (await request.json()) as { passcode?: unknown };
    passcode = typeof body.passcode === "string" ? body.passcode : "";
  } catch {
    /* empty body */
  }
  if (!passcode || !same(passcode, code)) {
    return Response.json({ unlocked: false, detail: "That passcode is not right." }, { status: 401 });
  }
  (await cookies()).set(COOKIE, sessionValue(code), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production" && !request.url.startsWith("http://localhost"),
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return Response.json({ unlocked: true, required: true });
}

export async function DELETE() {
  (await cookies()).delete(COOKIE);
  return Response.json({ unlocked: !passcodeRequired(), required: passcodeRequired() });
}
