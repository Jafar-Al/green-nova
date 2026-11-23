"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useOnline } from "@/lib/hooks";
import { DEMO_DETAIL, DEMO_NOTICE } from "@/lib/demo/notice";
import { IS_DEMO_MODE } from "@/lib/config";
import { IconAlert, IconInfo, IconMap, IconOffline, IconRefresh } from "./icons";
import { Button, cx } from "./primitives";

export function EmptyState({
  title,
  children,
  action,
  className,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("grid place-items-start gap-3 rounded-md border border-dashed border-line-strong p-5", className)}>
      <IconMap className="size-6 text-ink-3" />
      <div>
        <h3 className="h-panel text-ink">{title}</h3>
        {children ? <div className="mt-1.5 max-w-[56ch] text-sm text-ink-2">{children}</div> : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  className,
  detail,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
  detail?: string;
}) {
  return (
    <div role="alert" className={cx("grid gap-3 rounded-md border border-danger/60 bg-[color-mix(in_oklab,var(--danger)_8%,transparent)] p-5", className)}>
      <div className="flex items-start gap-3">
        <IconAlert className="mt-0.5 size-5 shrink-0 text-danger" />
        <div>
          <h3 className="h-panel text-ink">{title}</h3>
          <p className="mt-1 max-w-[60ch] text-sm text-ink-2">{message}</p>
          {detail ? <p className="mt-1 text-xs text-ink-3">{detail}</p> : null}
        </div>
      </div>
      {onRetry ? (
        <div>
          <Button size="sm" onClick={onRetry}>
            <IconRefresh className="size-4" />
            Try again
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** Shown only while the browser reports it is offline. */
export function OfflineBanner({ className }: { className?: string }) {
  const online = useOnline();
  if (online) return null;
  return (
    <div role="status" className={cx("flex items-start gap-3 rounded-md border border-warn/60 bg-[color-mix(in_oklab,var(--warn)_8%,transparent)] px-4 py-3 text-sm", className)}>
      <IconOffline className="mt-0.5 size-5 shrink-0 text-warn" />
      <p className="text-ink-2">
        <strong className="text-ink">You are offline.</strong> Data already loaded stays available. The satellite basemap may be incomplete and new analyses cannot be
        started until the connection returns.
      </p>
    </div>
  );
}

/** Inline explanation of what demonstration data means. Renders nothing for live data. */
export function DemoNote({ className, compact = false }: { className?: string; compact?: boolean }) {
  if (!IS_DEMO_MODE) return null;
  return (
    <div className={cx("flex items-start gap-3 rounded-md border border-dashed border-sand-500/70 px-3.5 py-3 text-sm", className)}>
      <IconInfo className="mt-0.5 size-4 shrink-0 text-warn" />
      <p className="text-ink-2">
        <strong className="text-ink">{DEMO_NOTICE}.</strong>
        {compact ? null : <> {DEMO_DETAIL}</>}{" "}
        <Link href="/#evidence" className="text-ink underline">
          What is real?
        </Link>
      </p>
    </div>
  );
}

/** Sits inside every map and data panel so the marker survives screenshots and cropping. */
export function DemoMapMarker({ className }: { className?: string }) {
  if (!IS_DEMO_MODE) return null;
  return (
    <p
      className={cx(
        "pointer-events-none m-0 inline-block rounded-xs bg-sand-300 px-2 py-1 text-xs font-bold tracking-wide text-[#1a1405] shadow-[0_1px_2px_rgb(0_0_0/0.4)]",
        className,
      )}
    >
      {DEMO_NOTICE}
    </p>
  );
}

export function LoadingLine({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-ink-2">
      <span aria-hidden="true" className="inline-block size-3 animate-spin rounded-full border-2 border-ink-3 border-t-transparent motion-reduce:animate-none" />
      {children}
    </p>
  );
}
