import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ShowcaseDetail, { CatalogueCreative } from "@/components/showcase/Detail";
import { catalogueOn } from "@/lib/catalogue";
import { readDetail, readIndex } from "@/lib/showcase";

export async function generateStaticParams() {
  const ix = await readIndex();
  return ix.creatives.map((c) => ({ id: c.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const id = (await params).id;
  const d = !catalogueOn() || (await readIndex()).creatives.some((c) => c.id === id) ? await readDetail(id) : null;
  return { title: d ? `${d.title} · CBJ Studio` : "Showcase · CBJ Studio", description: d?.tagline };
}

// The curated ten are static (generateStaticParams). With the catalogue on (SPEC-R2-CATALOGUE) every other id is read
// from the bucket in the browser, even when an older export left its files under public/showcase/ (the catalogue's copy
// is the one its gallery card shows); with it off, as before.
export default async function ShowcaseItemPage({ params }: { params: Promise<{ id: string }> }) {
  const id = (await params).id;
  const curated = !catalogueOn() || (await readIndex()).creatives.some((c) => c.id === id);
  const d = curated ? await readDetail(id) : null;
  if (d) return <ShowcaseDetail detail={d} />;
  if (catalogueOn() && /^[A-Za-z0-9_-]+$/.test(id)) return <CatalogueCreative key={id} id={id} />;
  notFound();
}
