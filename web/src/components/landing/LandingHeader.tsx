import Link from "next/link";
import { Logo } from "@/components/brand/Logo";
import { LinkButton } from "@/components/ui/primitives";

const LINKS = [
  { href: "#discover", label: "Discover" },
  { href: "#restore", label: "Restore" },
  { href: "#how", label: "How it works" },
  { href: "#evidence", label: "Evidence" },
] as const;

/** Sits over the hero image. Mobile menu is a native <details> (works without JavaScript, keyboard accessible). */
export function LandingHeader() {
  return (
    <header className="absolute inset-x-0 top-0 z-20">
      <div className="mx-auto flex max-w-[84rem] items-center justify-between gap-4 px-[var(--spacing-gutter)] py-4">
        <Logo cut="#0f2419" />
        <nav aria-label="Primary" className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} className="inline-flex min-h-10 items-center px-3 text-sm font-semibold text-ink-2 no-underline hover:text-ink">
              {l.label}
            </a>
          ))}
          <LinkButton href="/dashboard" variant="primary" size="sm" className="ms-3">
            Open dashboard
          </LinkButton>
        </nav>
        <details className="group relative md:hidden">
          <summary className="btn btn-secondary btn-sm cursor-pointer list-none [&::-webkit-details-marker]:hidden">
            <span className="group-open:hidden">Menu</span>
            <span className="hidden group-open:inline">Close</span>
          </summary>
          <nav aria-label="Primary mobile" className="absolute end-0 top-full z-30 mt-2 grid w-56 gap-0.5 rounded-md border border-line-strong bg-canvas p-2 shadow-[0_12px_30px_rgb(0_0_0/0.5)]">
            {LINKS.map((l) => (
              <a key={l.href} href={l.href} className="flex min-h-11 items-center rounded-sm px-3 text-sm font-semibold text-ink no-underline hover:bg-[color-mix(in_oklab,var(--ink)_8%,transparent)]">
                {l.label}
              </a>
            ))}
            <Link href="/dashboard" className="btn btn-primary mt-1 no-underline">
              Open dashboard
            </Link>
          </nav>
        </details>
      </div>
    </header>
  );
}
