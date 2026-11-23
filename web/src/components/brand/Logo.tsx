import Link from "next/link";

/** Mark: an orbit ring (the satellite view) holding a single leaf cut by a contour line. */
export function LogoMark({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true" focusable="false">
      <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8.6 21.4C8.6 14.6 13 10.6 22.8 10.2c.5 9.2-3.8 13.6-10.2 13.6-1.4 0-2.8-.3-4-.8Z" fill="currentColor" />
      <path d="M9.6 24.6c3.2-4.6 6.4-7.4 10.6-9.2" fill="none" stroke="var(--logo-cut, #0f2419)" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return <span className={`wordmark ${className ?? ""}`}>Green Nova AI</span>;
}

export function Logo({ href = "/", cut, compact = false }: { href?: string; cut?: string; compact?: boolean }) {
  return (
    <Link
      href={href}
      aria-label="GREEN NOVA AI, home"
      className="inline-flex min-h-10 items-center gap-2.5 text-ink no-underline"
      style={cut ? ({ ["--logo-cut" as string]: cut } as React.CSSProperties) : undefined}
    >
      <LogoMark />
      <Wordmark className={compact ? "hidden min-[480px]:inline" : ""} />
    </Link>
  );
}
