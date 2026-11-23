"use client";

import { useMemo, useState } from "react";
import type { SuitabilityFeature } from "@/lib/contract";
import { SUITABILITY_CLASSES } from "@/lib/classes";
import { fmtConfidence, fmtDunum, fmtHa } from "@/lib/format";
import { Button, ClassSwatch, cx } from "@/components/ui/primitives";

type SortKey = "area" | "confidence" | "id";
const PAGE = 40;

/**
 * Keyboard-accessible alternative to clicking polygons on the map, and a sortable index of every land unit.
 * `multi` shows checkboxes (restoration selection); otherwise rows are single-select buttons.
 */
export function PolygonList({
  features,
  selectedIds,
  focusId,
  onToggle,
  onFocus,
  multi = false,
  isDisabled,
  label,
  maxHeightClass = "max-h-80",
}: {
  features: SuitabilityFeature[];
  selectedIds: string[];
  focusId?: string | null;
  onToggle?: (id: string) => void;
  onFocus?: (id: string) => void;
  multi?: boolean;
  isDisabled?: (f: SuitabilityFeature) => string | null;
  label: string;
  maxHeightClass?: string;
}) {
  const [sort, setSort] = useState<SortKey>("area");
  const [shown, setShown] = useState(PAGE);
  const sorted = useMemo(() => {
    const a = features.slice();
    if (sort === "area") a.sort((x, y) => y.properties.area_ha - x.properties.area_ha);
    if (sort === "confidence") a.sort((x, y) => y.properties.confidence - x.properties.confidence);
    if (sort === "id") a.sort((x, y) => x.properties.id.localeCompare(y.properties.id, undefined, { numeric: true }));
    return a;
  }, [features, sort]);
  const sel = new Set(selectedIds);
  const rows = sorted.slice(0, shown);

  return (
    <section aria-label={label}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="h-panel">
          {label} <span className="font-normal text-ink-3 tnum">({features.length})</span>
        </h3>
        <div className="flex items-center gap-2">
          <label htmlFor="poly-sort" className="text-xs text-ink-3">
            Sort by
          </label>
          <select id="poly-sort" className="field !min-h-8 !w-auto !py-0 text-xs" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            <option value="area">Largest area</option>
            <option value="confidence">Highest confidence</option>
            <option value="id">Unit id</option>
          </select>
        </div>
      </div>
      {features.length === 0 ? (
        <p className="rounded-sm border border-dashed border-line-strong p-3 text-sm text-ink-2">No land units match the current filters.</p>
      ) : (
        <ul className={cx("m-0 list-none divide-y divide-line overflow-y-auto rounded-sm border border-line p-0", maxHeightClass)}>
          {rows.map((f) => {
            const p = f.properties;
            const blocked = isDisabled?.(f) ?? null;
            const isSel = sel.has(p.id);
            const isFocus = focusId === p.id;
            const descId = `pl-${p.id}`;
            return (
              <li key={p.id} className={cx(isFocus && "bg-[color-mix(in_oklab,var(--accent)_12%,transparent)]")}>
                <div className="flex items-center gap-2 px-2 py-1.5">
                  {multi ? (
                    <input
                      type="checkbox"
                      className="size-4 shrink-0"
                      checked={isSel}
                      disabled={!!blocked}
                      onChange={() => onToggle?.(p.id)}
                      aria-label={`Select ${p.id}`}
                      aria-describedby={descId}
                    />
                  ) : null}
                  <button
                    type="button"
                    onClick={() => (multi ? onFocus?.(p.id) : onToggle?.(p.id))}
                    aria-pressed={multi ? undefined : isSel}
                    aria-describedby={descId}
                    className="grid min-h-10 min-w-0 flex-1 grid-cols-[auto_1fr_auto] items-center gap-2.5 rounded-xs text-start hover:bg-[color-mix(in_oklab,var(--ink)_6%,transparent)]"
                  >
                    <ClassSwatch code={p.class_code} size="sm" />
                    <span className="min-w-0">
                      <span className="block truncate font-mono text-xs text-ink">{p.id}</span>
                      <span className="block text-xs text-ink-3">{SUITABILITY_CLASSES[p.class_code].short}</span>
                    </span>
                    <span className="text-end text-xs text-ink-2 tnum">
                      <span className="block">{fmtHa(p.area_ha)} ha</span>
                      <span className="block text-ink-3">
                        {fmtDunum(p.area_dunum)} dunum &middot; conf {fmtConfidence(p.confidence)}
                      </span>
                    </span>
                  </button>
                </div>
                <span id={descId} className="visually-hidden">
                  Class {p.class_code}, {fmtHa(p.area_ha)} hectares, confidence {fmtConfidence(p.confidence)}.{blocked ? ` ${blocked}` : ""}
                </span>
                {blocked && multi ? <p className="m-0 px-3 pb-2 ps-10 text-xs text-ink-3">{blocked}</p> : null}
              </li>
            );
          })}
        </ul>
      )}
      {shown < sorted.length ? (
        <div className="mt-2">
          <Button size="sm" variant="ghost" onClick={() => setShown((n) => n + PAGE)}>
            Show {Math.min(PAGE, sorted.length - shown)} more of {sorted.length - shown}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
