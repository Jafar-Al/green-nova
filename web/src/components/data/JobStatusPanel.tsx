"use client";

import type { ReactNode } from "react";
import type { AnalysisJob } from "@/lib/types";
import { IS_DEMO_MODE } from "@/lib/config";
import { fmtDateTime } from "@/lib/format";
import { Button, CheckRow, cx } from "@/components/ui/primitives";
import { ErrorState } from "@/components/ui/states";
import { IconCheck, IconPlay, IconRefresh, IconStop } from "@/components/ui/icons";

const STATE_LABEL: Record<AnalysisJob["state"], string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** Job lifecycle UI: idle, starting, queued, running (with progress), complete, failed, cancelled, start error. */
export function JobStatusPanel({
  title,
  idleText,
  startLabel,
  job,
  error,
  starting,
  onStart,
  onCancel,
  startBlockedReason,
  simulateFailure,
  onSimulateFailure,
  completeNote,
  idPrefix,
}: {
  title: string;
  idleText: ReactNode;
  startLabel: string;
  job: AnalysisJob | null;
  error: { message: string; code?: string } | null;
  starting: boolean;
  onStart: () => void;
  onCancel: () => void;
  startBlockedReason?: string | null;
  simulateFailure: boolean;
  onSimulateFailure: (v: boolean) => void;
  completeNote?: ReactNode;
  idPrefix: string;
}) {
  const active = job && (job.state === "queued" || job.state === "running");
  const pct = Math.round((job?.progress ?? 0) * 100);
  const blockedId = `${idPrefix}-blocked`;
  return (
    <section aria-labelledby={`${idPrefix}-title`} className="grid gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 id={`${idPrefix}-title`} className="h-panel">
          {title}
        </h3>
        {job ? (
          <span
            className={cx(
              "text-xs font-semibold",
              job.state === "succeeded" ? "text-ok" : job.state === "failed" ? "text-danger" : job.state === "cancelled" ? "text-warn" : "text-ink-2",
            )}
          >
            {STATE_LABEL[job.state]}
            {job.demo ? " (demo run)" : ""}
          </span>
        ) : null}
      </div>

      <p role="status" aria-live="polite" className="visually-hidden">
        {job ? `${STATE_LABEL[job.state]}. ${job.message}` : ""}
      </p>

      {!job && !error ? <div className="text-sm text-ink-2">{idleText}</div> : null}

      {active && job ? (
        <div className="grid gap-2">
          <div
            role="progressbar"
            aria-label={`${title} progress`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            aria-valuetext={`${pct} percent. ${job.message}`}
            className="h-2 overflow-hidden rounded-xs bg-[color-mix(in_oklab,var(--ink)_14%,transparent)]"
          >
            <div className="h-full bg-accent transition-[inline-size] duration-300 ease-out" style={{ inlineSize: `${Math.max(4, pct)}%` }} />
          </div>
          <p className="m-0 flex justify-between gap-2 text-xs text-ink-2">
            <span>{job.message}</span>
            <span className="tnum">{pct}%</span>
          </p>
          <ol className="m-0 grid list-none gap-0.5 p-0 text-xs text-ink-3">
            {job.stages.map((s) => (
              <li key={s} className={cx("flex items-center gap-2", s === job.message && "font-semibold text-ink")}>
                <span aria-hidden="true" className={cx("size-1.5 rounded-full", s === job.message ? "bg-accent" : "bg-line-strong")} />
                {s}
              </li>
            ))}
          </ol>
          <div>
            <Button size="sm" onClick={onCancel}>
              <IconStop className="size-4" />
              Cancel run
            </Button>
          </div>
        </div>
      ) : null}

      {job?.state === "succeeded" ? (
        <div className="flex items-start gap-2 rounded-sm border border-ok/50 px-3 py-2.5 text-sm text-ink-2">
          <IconCheck className="mt-0.5 size-4 shrink-0 text-ok" />
          <div>
            <p className="m-0 text-ink">Analysis complete{job.finished_at ? ` · ${fmtDateTime(job.finished_at)}` : ""}.</p>
            {completeNote ? <div className="mt-1 text-xs text-ink-3">{completeNote}</div> : null}
          </div>
        </div>
      ) : null}

      {job?.state === "failed" ? <ErrorState title="The analysis failed" message={job.error?.message ?? "The job ended with an error."} detail={job.error?.recoverable ? "This is recoverable: start the analysis again." : undefined} /> : null}
      {job?.state === "cancelled" ? <p className="m-0 rounded-sm border border-warn/50 px-3 py-2 text-sm text-ink-2">The run was cancelled. No results were produced.</p> : null}
      {error && !job ? <ErrorState title="Could not start the analysis" message={error.message} /> : null}
      {error && job ? <ErrorState title="Lost contact with the job" message={error.message} /> : null}

      {!active ? (
        <div className="grid gap-2">
          <Button variant="primary" onClick={onStart} disabled={starting || !!startBlockedReason} aria-describedby={startBlockedReason ? blockedId : undefined}>
            {job?.state === "succeeded" ? <IconRefresh className="size-4" /> : <IconPlay className="size-4" />}
            {starting ? "Starting…" : job?.state === "succeeded" ? "Run again" : job?.state === "failed" || job?.state === "cancelled" ? "Start again" : startLabel}
          </Button>
          {startBlockedReason ? (
            <p id={blockedId} className="m-0 text-xs text-ink-3">
              {startBlockedReason}
            </p>
          ) : null}
        </div>
      ) : null}

      {IS_DEMO_MODE ? (
        <details className="rounded-sm border border-line px-3 text-sm">
          <summary className="flex min-h-9 cursor-pointer items-center text-xs font-semibold text-ink-2">Demo controls</summary>
          <div className="pb-2">
            <CheckRow id={`${idPrefix}-fail`} checked={simulateFailure} onChange={onSimulateFailure} disabled={!!active}>
              <span className="text-xs">Simulate a failed run (shows the error state)</span>
            </CheckRow>
            <p className="m-0 text-xs text-ink-3">Demo runs are timers that replay precomputed synthetic results. No model is executed.</p>
          </div>
        </details>
      ) : null}
    </section>
  );
}
