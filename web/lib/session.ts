import "server-only";
import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

// The passcode gate (SPEC §1.5, §2). Running the engine costs the owner time and model credits, so when
// STUDIO_PASSCODE is set, the actions that start work need a session cookie; browsing never does.

export const COOKIE = "cbj_studio";

export function engineUrl(): string {
  return (process.env.ENGINE_URL || "").trim().replace(/\/+$/, "");
}

export function engineToken(): string {
  return (process.env.ENGINE_TOKEN || "").trim();
}

export function passcodeRequired(): boolean {
  return Boolean(process.env.STUDIO_PASSCODE);
}

export function sessionValue(passcode: string): string {
  const secret = process.env.SESSION_SECRET;
  return secret
    ? createHmac("sha256", secret).update(passcode).digest("hex")
    : createHash("sha256").update(passcode).digest("hex");
}

export function same(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export async function isUnlocked(): Promise<boolean> {
  const code = process.env.STUDIO_PASSCODE;
  if (!code) return true;
  const got = (await cookies()).get(COOKIE)?.value;
  return Boolean(got) && same(got as string, sessionValue(code));
}
