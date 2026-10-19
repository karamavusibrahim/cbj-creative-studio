import { cookies } from "next/headers";
import { COOKIE, engineToken, engineUrl, isUnlocked, passcodeRequired, same, sessionValue } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function GET() {
  const unlocked = await isUnlocked();
  const required = passcodeRequired();
  if (!unlocked) return Response.json({ unlocked: false, required });
  return Response.json({ unlocked: true, required, engine: { url: engineUrl(), token: engineToken() } });
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
