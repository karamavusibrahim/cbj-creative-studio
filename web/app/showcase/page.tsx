import type { Metadata } from "next";
import Gallery from "@/components/showcase/Gallery";
import { readIndex } from "@/lib/showcase";

export const metadata: Metadata = { title: "Showcase · CBJ Studio" };

export default async function ShowcasePage() {
  return <Gallery index={await readIndex()} />;
}
