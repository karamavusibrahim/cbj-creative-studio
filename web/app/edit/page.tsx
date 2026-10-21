import type { Metadata } from "next";
import EditWorkspace from "@/components/edit/EditWorkspace";

export const metadata: Metadata = { title: "Edit · CBJ Studio" };

export default async function EditPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const one = (k: string) => (Array.isArray(sp[k]) ? sp[k]?.[0] : sp[k]) as string | undefined;
  const c = one("c");
  const v = Number(one("v"));
  const cid = c && /^[A-Za-z0-9_-]{1,120}$/.test(c) ? c : undefined;
  return <EditWorkspace cid={cid} n={Number.isFinite(v) && v > 0 ? v : undefined} prefill={one("prompt")} matched={one("matched") === "1"} />;
}
