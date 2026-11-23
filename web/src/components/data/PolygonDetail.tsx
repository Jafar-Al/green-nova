"use client";

import Link from "next/link";
import type { SuitabilityFeature } from "@/lib/contract";
import { CLASS_LIST, CLASS5_NOTE, CONFIDENCE_EXPLAINER } from "@/lib/classes";
import { fmtConfidence, fmtDunum, fmtHa } from "@/lib/format";
import { formatLatLon } from "@/lib/geo";
import { DUNUM_DEFINITION } from "@/lib/units";
import { ClassChip, Disclosure, KV, Meter, cx } from "@/components/ui/primitives";
import { DemoNote } from "@/components/ui/states";
import { IconArrowRight } from "@/components/ui/icons";
import { FactorList } from "./FactorList";

export function ProbabilityBars({ probs }: { probs: SuitabilityFeature["properties"]["class_probabilities"] }) {
  return (
    <ul className="m-0 grid list-none gap-1.5 p-0">
      {CLASS_LIST.map((c) => {
        const v = probs[c.key] ?? 0;
        return (
          <li key={c.code} className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-2 text-xs">
            <span className="truncate text-ink-2">
              {c.code}. {c.short}
            </span>
            <Meter value={v} label={`Class ${c.code} probability`} color={c.color} />
            <span className="text-end text-ink tnum">{fmtConfidence(v)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Detail panel for one Model 1 land unit. `restorationLink` shows a pointer to Model 2 for class 3/4. */
export function PolygonDetail({ feature, onClear, className, compact = false }: { feature: SuitabilityFeature; onClear?: () => void; className?: string; compact?: boolean }) {
  const p = feature.properties;
  const [lon, lat] = p.centroid;
  return (
    <article aria-label={`Land unit ${p.id}`} className={cx("grid gap-4", className)}>
      <header className="grid gap-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="m-0 break-all font-mono text-xs text-ink-3">{p.id}</p>
            <h3 className="h-panel mt-1">
              <ClassChip code={p.class_code} />
            </h3>
          </div>
          {onClear ? (
            <button type="button" onClick={onClear} className="btn btn-ghost btn-sm shrink-0">
              Clear
            </button>
          ) : null}
        </div>
        {p.class_code === 5 ? <p className="m-0 text-sm text-ink-2">{CLASS5_NOTE}</p> : null}
      </header>

      <dl className="m-0">
        <KV k="Area">
          <span className="tnum">
            {fmtHa(p.area_ha)} ha &middot; {fmtDunum(p.area_dunum)} dunum
          </span>
          <span className="block text-xs text-ink-3">{DUNUM_DEFINITION}</span>
        </KV>
        <KV k="Centroid">
          <span className="font-mono text-xs">{formatLatLon(lon, lat, 4)}</span>
        </KV>
        <KV k="Resolution">
          <span className="tnum">{p.effective_resolution_m} m</span> <span className="text-xs text-ink-3">effective; the unit is no more precise than this</span>
        </KV>
        <KV k="Confidence">
          <span className="flex items-center gap-3">
            <span className="w-10 font-semibold tnum">{fmtConfidence(p.confidence)}</span>
            <Meter value={p.confidence} label="Confidence" className="flex-1" />
          </span>
        </KV>
      </dl>

      <Disclosure summary="How confidence is defined" className="-mt-2 rounded-sm border border-line px-3">
        <p className="m-0 text-xs text-ink-2">
          <strong className="text-ink">This record:</strong> {p.confidence_method}
        </p>
        <p className="mt-2 text-xs text-ink-3">{CONFIDENCE_EXPLAINER}</p>
      </Disclosure>

      {!compact ? (
        <section aria-labelledby={`probs-${p.id}`}>
          <h4 id={`probs-${p.id}`} className="h-panel mb-2">
            Class probabilities
          </h4>
          <ProbabilityBars probs={p.class_probabilities} />
        </section>
      ) : null}

      <section aria-labelledby={`factors-${p.id}`}>
        <h4 id={`factors-${p.id}`} className="h-panel">
          Factors behind this class
        </h4>
        <FactorList factors={compact ? p.factors.filter((f) => f.status !== "favourable").slice(0, 4) : p.factors} />
        {compact ? <p className="mt-1 text-xs text-ink-3">Showing the limiting and marginal factors. Open the full record for all of them.</p> : null}
      </section>

      <section className="text-xs text-ink-3">
        <p className="m-0">
          Model version <span className="font-mono text-ink-2">{p.provenance.model_version}</span>. Label basis:{" "}
          {typeof p.provenance.label_basis === "string" ? p.provenance.label_basis : "per class (see run metadata)"}.
        </p>
      </section>

      <DemoNote compact />

      <Link
        href={`/land/${encodeURIComponent(p.id)}`}
        className="btn btn-primary no-underline"
        aria-label={`Open the full land details for ${p.id}`}
      >
        Open full land details
        <IconArrowRight className="size-4" />
      </Link>
    </article>
  );
}
