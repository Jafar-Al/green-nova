"use client";

import type { ReactNode } from "react";
import { CLASS_LIST, FEASIBILITY_META } from "@/lib/classes";
import type { FeasibilityClass, SuitabilityClassCode } from "@/lib/contract";
import { CONFIDENCE_BINS } from "@/lib/layers";
import { ClassSwatch } from "@/components/ui/primitives";
import { IconChevronDown } from "@/components/ui/icons";
import { useMediaQuery } from "@/lib/hooks";

export type LegendMode = "class" | "confidence" | "restoration" | "simulated";

function Row({ swatch, label, note }: { swatch: ReactNode; label: string; note?: string }) {
  return (
    <li className="flex items-center gap-2.5 py-0.5">
      {swatch}
      <span className="text-xs leading-snug text-ink">
        {label}
        {note ? <span className="text-ink-3"> &middot; {note}</span> : null}
      </span>
    </li>
  );
}

/** Collapsible so it never hides the map on small screens. Counts are optional. */
export function MapLegend({
  mode,
  counts,
  defaultOpen = true,
}: {
  mode: LegendMode;
  counts?: Partial<Record<SuitabilityClassCode | FeasibilityClass, number>>;
  defaultOpen?: boolean;
}) {
  const wide = useMediaQuery("(min-width: 768px)");
  const title =
    mode === "class" ? "Suitability class" : mode === "confidence" ? "Confidence" : mode === "restoration" ? "Restoration feasibility" : "Simulated post-restoration class";
  return (
    <details open={defaultOpen && wide} className="group w-60 max-w-full rounded-sm border border-line-strong bg-[color-mix(in_oklab,var(--canvas)_92%,transparent)] shadow-[0_6px_16px_rgb(0_0_0/0.35)]">
      <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-2 px-2.5 text-xs font-semibold text-ink [&::-webkit-details-marker]:hidden">
        <span>
          Legend <span className="font-normal text-ink-3">&middot; {title}</span>
        </span>
        <IconChevronDown className="size-3.5 text-ink-3 transition-transform group-open:rotate-180" />
      </summary>
      <ul className="m-0 list-none px-2.5 pb-2 pt-0.5">
        {(mode === "class" || mode === "simulated") &&
          CLASS_LIST.filter((c) => mode === "class" || c.code !== 5).map((c) => (
            <Row
              key={c.code}
              swatch={<ClassSwatch code={c.code} size="sm" />}
              label={c.short}
              note={counts?.[c.code] !== undefined ? String(counts[c.code]) : c.hatch ? "hatched" : undefined}
            />
          ))}
        {mode === "confidence" &&
          CONFIDENCE_BINS.map((b) => (
            <Row key={b.min} swatch={<span aria-hidden="true" className="size-5 shrink-0 rounded-xs" style={{ background: b.color }} />} label={b.label} />
          ))}
        {mode === "restoration" && (
          <>
            {(["high", "moderate", "low", "not_feasible"] as FeasibilityClass[]).map((k) => (
              <Row
                key={k}
                swatch={<span aria-hidden="true" className="size-5 shrink-0 rounded-xs" style={{ background: FEASIBILITY_META[k].color }} />}
                label={FEASIBILITY_META[k].label}
                note={counts?.[k] !== undefined ? String(counts[k]) : undefined}
              />
            ))}
            <Row swatch={<span aria-hidden="true" className="size-5 shrink-0 rounded-xs border border-dashed border-ink-3 bg-[#8a948d]/20" />} label="Not in Model 2 scope" note="muted" />
          </>
        )}
      </ul>
      {mode === "simulated" ? (
        <p className="m-0 border-t border-line px-2.5 py-1.5 text-xs text-ink-2">Dashed outline + hatch = SIMULATED outcome, not an observed result.</p>
      ) : null}
      {mode === "class" ? <p className="m-0 border-t border-line px-2.5 py-1.5 text-xs text-ink-3">Hatched = excluded by restriction.</p> : null}
    </details>
  );
}
