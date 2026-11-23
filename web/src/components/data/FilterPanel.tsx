"use client";

import { CLASS_LIST } from "@/lib/classes";
import type { SuitabilityClassCode } from "@/lib/contract";
import { ALL_CLASSES, defaultSuitabilityFilters, type SuitabilityFilters } from "@/lib/layers";
import { fmtConfidence, fmtInt } from "@/lib/format";
import { Button, CheckRow, ClassSwatch } from "@/components/ui/primitives";

const AREA_OPTIONS = [0, 10, 50, 100, 500, 1000];

/** Class, confidence and minimum-area filters. The map, list and statistics all read the same filter state. */
export function FilterPanel({
  value,
  onChange,
  counts,
  idPrefix,
  shown,
  total,
}: {
  value: SuitabilityFilters;
  onChange: (v: SuitabilityFilters) => void;
  counts: Partial<Record<SuitabilityClassCode, number>>;
  idPrefix: string;
  shown: number;
  total: number;
}) {
  const toggle = (c: SuitabilityClassCode, on: boolean) => {
    const next = new Set(value.classes);
    if (on) next.add(c);
    else next.delete(c);
    onChange({ ...value, classes: next });
  };
  const isDefault = value.classes.size === ALL_CLASSES.length && value.minConfidence === 0 && value.minAreaHa === 0;
  return (
    <fieldset className="m-0 grid min-w-0 gap-3 border-0 p-0">
      <legend className="h-panel mb-1 flex w-full items-center justify-between gap-2">
        <span>Filters</span>
        <span className="text-xs font-normal text-ink-3 tnum" aria-live="polite">
          {fmtInt(shown)} of {fmtInt(total)} units shown
        </span>
      </legend>
      <div>
        <p className="label mb-1">Suitability class</p>
        {CLASS_LIST.map((c) => (
          <CheckRow key={c.code} id={`${idPrefix}-cls-${c.code}`} checked={value.classes.has(c.code)} onChange={(on) => toggle(c.code, on)}>
            <ClassSwatch code={c.code} size="sm" />
            <span className="flex-1">{c.short}</span>
            <span className="text-xs text-ink-3 tnum">{counts[c.code] ?? 0}</span>
          </CheckRow>
        ))}
      </div>
      <div>
        <label htmlFor={`${idPrefix}-conf`} className="mb-1 flex items-baseline justify-between text-sm font-semibold text-ink">
          <span>Minimum confidence</span>
          <span className="font-normal text-ink-2 tnum">{fmtConfidence(value.minConfidence)}</span>
        </label>
        <input
          id={`${idPrefix}-conf`}
          type="range"
          min={0}
          max={0.9}
          step={0.05}
          value={value.minConfidence}
          onChange={(e) => onChange({ ...value, minConfidence: Number(e.target.value) })}
          className="h-6 w-full"
        />
        <p className="m-0 text-xs text-ink-3">Confidence is defined per record; see the detail panel.</p>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-area`} className="mb-1 block text-sm font-semibold text-ink">
          Minimum area
        </label>
        <select id={`${idPrefix}-area`} className="field" value={value.minAreaHa} onChange={(e) => onChange({ ...value, minAreaHa: Number(e.target.value) })}>
          {AREA_OPTIONS.map((a) => (
            <option key={a} value={a}>
              {a === 0 ? "Any size" : `${fmtInt(a)} ha and larger (${fmtInt(a * 10)} dunum)`}
            </option>
          ))}
        </select>
      </div>
      <div>
        <Button size="sm" variant="ghost" onClick={() => onChange(defaultSuitabilityFilters())} disabled={isDefault}>
          Reset filters
        </Button>
      </div>
    </fieldset>
  );
}
