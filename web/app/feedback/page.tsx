import type { Metadata } from "next";
import OwnerPage, { type OwnerQuery } from "@/components/feedback/OwnerPage";

export const metadata: Metadata = { title: "Feedback · CBJ Studio" };

export default async function FeedbackPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const one = (k: string) => {
    const x = Array.isArray(sp[k]) ? sp[k]?.[0] : sp[k];
    return typeof x === "string" ? x.slice(0, 200) : "";
  };
  const q: OwnerQuery = {
    tab: one("tab") === "lessons" ? "lessons" : "records",
    designer: one("designer"),
    area: one("area"),
    kind: one("kind"),
    creative: /^[A-Za-z0-9_-]{1,120}$/.test(one("creative")) ? one("creative") : "",
    id: /^fb-[A-Za-z0-9-]{1,60}$/.test(one("id")) ? one("id") : "",
  };
  return <OwnerPage initial={q} />;
}
