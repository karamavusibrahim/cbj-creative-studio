// The engine the QA scripts read from directly (GETs only, from node): ENGINE_URL / ENGINE_TOKEN from the environment,
// else from web/.env.local (the same values the site's server uses), else the local dev engine on :8765.
import { readFileSync } from "node:fs";

function envLocal() {
  try {
    const text = readFileSync(new URL("../.env.local", import.meta.url), "utf8");
    return Object.fromEntries(
      text
        .split("\n")
        .map((l) => /^([A-Z_]+)=(.*)$/.exec(l.trim()))
        .filter(Boolean)
        .map((m) => [m[1], m[2].trim()]),
    );
  } catch {
    return {};
  }
}

const local = envLocal();
export const ENGINE = (process.env.ENGINE_URL || local.ENGINE_URL || "http://127.0.0.1:8765").replace(/\/$/, "");
const TOKEN = process.env.ENGINE_TOKEN ?? local.ENGINE_TOKEN ?? "";

/** The engine's Authorization header (none when it has no token). */
export const engineAuth = () => (TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {});

/** GET a JSON answer from the engine (with its token, if any); throws on an HTTP error. */
export async function engineJson(path) {
  const r = await fetch(ENGINE + path, { headers: TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {} });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}
