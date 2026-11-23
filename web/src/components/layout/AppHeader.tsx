"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/brand/Logo";
import { cx } from "@/components/ui/primitives";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/suitability", label: "Suitability" },
  { href: "/restoration", label: "Restoration" },
] as const;

/** Workspace header: sticky below the demonstration bar. */
export function AppHeader() {
  const path = usePathname();
  return (
    <header
      className="sticky z-50 flex items-center justify-between gap-2 border-b border-line bg-canvas px-[var(--spacing-gutter)] sm:gap-4"
      style={{ insetBlockStart: "var(--demo-h)", blockSize: "var(--app-h)" }}
    >
      <div className="flex items-center gap-6">
        <Logo compact />
      </div>
      <nav aria-label="Workspace" className="flex min-w-0 items-center gap-0 sm:gap-1">
        {NAV.map((n) => {
          const current = path === n.href || (n.href === "/suitability" && path.startsWith("/land"));
          return (
            <Link
              key={n.href}
              href={n.href}
              aria-current={path === n.href ? "page" : undefined}
              className={cx(
                "relative inline-flex min-h-10 items-center px-2 text-[0.8125rem] font-semibold no-underline transition-colors duration-150 sm:px-3 sm:text-sm",
                path === n.href ? "text-ink" : "text-ink-2 hover:text-ink",
              )}
            >
              {n.label}
              {current && path === n.href ? <span aria-hidden="true" className="absolute inset-x-2 -bottom-px h-0.5 bg-accent sm:inset-x-3" /> : null}
            </Link>
          );
        })}
        <Link href="/" className="ms-2 hidden min-h-10 items-center px-2 text-sm text-ink-3 hover:text-ink sm:inline-flex">
          Overview
        </Link>
      </nav>
    </header>
  );
}
