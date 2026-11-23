import type { SuitabilityFactor } from "@/lib/contract";
import { FACTOR_STATUS_META, factorLabel } from "@/lib/classes";
import { fmtNum } from "@/lib/format";
import { EvidenceBadge, FactorStatusBadge } from "@/components/ui/primitives";

const val = (f: SuitabilityFactor): string => {
  if (f.value === null) return "n/a";
  if (typeof f.value === "number") return `${fmtNum(f.value, 2)}${f.unit ? ` ${f.unit}` : ""}`;
  return f.value;
};

/** Factors behind a class, worst first. Each carries status, evidence class and the note that explains it. */
export function FactorList({ factors }: { factors: SuitabilityFactor[] }) {
  const sorted = factors
    .slice()
    .sort((a, b) => FACTOR_STATUS_META[b.status].rank - FACTOR_STATUS_META[a.status].rank || (b.importance ?? 0) - (a.importance ?? 0));
  return (
    <ul className="m-0 list-none divide-y divide-line p-0">
      {sorted.map((f) => (
        <li key={f.name} className="grid gap-1 py-2.5">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <span className="text-sm font-semibold text-ink">{factorLabel(f.name)}</span>
            <span className="text-sm text-ink tnum">{val(f)}</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <FactorStatusBadge status={f.status} />
            <EvidenceBadge evidence={f.evidence} />
            {f.importance !== undefined ? <span className="text-xs text-ink-3">importance {fmtNum(f.importance, 2, 2)}</span> : null}
          </div>
          {f.note ? <p className="m-0 text-xs text-ink-3">{f.note}</p> : null}
        </li>
      ))}
    </ul>
  );
}
