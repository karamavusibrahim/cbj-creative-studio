import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-start gap-3 py-16">
      <h1 className="font-headline text-headline-xl-mobile text-on-surface">Not found</h1>
      <p className="text-body-md text-on-surface-variant">This page or creative does not exist.</p>
      <div className="flex gap-4">
        <Link href="/" className="text-label-md font-semibold text-primary hover:underline">
          Create a creative
        </Link>
        <Link href="/showcase" className="text-label-md font-semibold text-primary hover:underline">
          Browse the showcase
        </Link>
      </div>
    </div>
  );
}
