"use client";

import type { FeasibilityClass, RestorationFeature, RestorationScenario, SuitabilityClassCode } from "@/lib/contract";
import { CLASS_LIST, FEASIBILITY_META, REVERSIBILITY_META, SUITABILITY_CLASSES, factorLabel } from "@/lib/classes";
import { fmtDunum, fmtHa, fmtNum, fmtRange } from "@/lib/format";
import { FEASIBILITY_ORDER, scenarioKey, type Outcome, type PolygonEvaluation } from "@/lib/restoration";
import type { RestorationConstraints } from "@/lib/types";
import { CheckRow, ClassSwatch, EvidenceBadge, FieldLabel, Meter } from "@/components/ui/primitives";

export function FeasibilityChip({ cls }: { cls: FeasibilityClass }) {
  const m = FEASIBILITY_META[cls];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink">
      <span aria-hidden="true" className="inline-block size-3.5 rounded-xs" style={{ background: m.color }} />
      {m.label}
    </span>
  );
}

/** Range bar: band = low..high, tick = central. Always paired with the numbers in text. */
export function WaterRange({ w, max }: { w: RestorationScenario["water_requirement_m3_ha_yr"]; max: number }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <div>
      <div
        role="img"
        aria-label={`Water requirement ${fmtNum(w.low, 0)} to ${fmtNum(w.high, 0)} cubic metres per hectare per year, central ${fmtNum(w.central, 0)}. Simulated range.`}
        className="relative h-3 rounded-xs bg-[color-mix(in_oklab,var(--ink)_10%,transparent)]"
      >
        <span className="absolute inset-y-0 rounded-xs bg-[color-mix(in_oklab,var(--accent)_55%,transparent)]" style={{ insetInlineStart: pct(w.low), inlineSize: `calc(${pct(w.high)} - ${pct(w.low)})` }} />
        <span className="absolute -inset-y-0.5 w-0.5 bg-ink" style={{ insetInlineStart: pct(w.central) }} />
      </div>
      <p className="m-0 mt-1 text-xs text-ink-2 tnum">
        {fmtRange(w.low, w.high)} <span className="text-ink-3">m&sup3;/ha/yr &middot; central {fmtNum(w.central, 0)}</span>
      </p>
    </div>
  );
}

export function LimitingFactorList({ factors }: { factors: RestorationFeature["properties"]["limiting_factors"] }) {
  if (factors.length === 0) return <p className="m-0 text-sm text-ink-2">Model 2 lists no limiting factors for this unit.</p>;
  return (
    <ul className="m-0 grid list-none gap-0 divide-y divide-line p-0">
      {factors
        .slice()
        .sort((a, b) => b.severity - a.severity)
        .map((l) => (
          <li key={l.factor} className="grid gap-1.5 py-2.5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm font-semibold text-ink">{factorLabel(l.factor)}</span>
              <span className="text-xs font-semibold text-ink-2">{REVERSIBILITY_META[l.reversibility]}</span>
            </div>
            <div className="grid grid-cols-[4.5rem_1fr_2.2rem] items-center gap-2 text-xs text-ink-3">
              <span>Severity</span>
              <Meter value={l.severity} label={`${factorLabel(l.factor)} severity`} color="var(--danger)" />
              <span className="text-end text-ink tnum">{fmtNum(l.severity, 2, 2)}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <EvidenceBadge evidence={l.evidence} />
            </div>
            <p className="m-0 text-xs text-ink-3">{l.detail}</p>
          </li>
        ))}
    </ul>
  );
}

export function InterventionList({ interventions }: { interventions: RestorationFeature["properties"]["interventions"] }) {
  return (
    <ul className="m-0 grid list-none divide-y divide-line p-0">
      {interventions.map((i) => (
        <li key={i.id} className="grid gap-1 py-2.5">
          <p className="m-0 text-sm font-semibold text-ink">{i.name}</p>
          <p className="m-0 text-xs text-ink-2">{i.description}</p>
          <p className="m-0 text-xs text-ink-3">
            Targets: {factorLabel(i.targets_factor)}. Expected effect: {i.expected_effect}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <EvidenceBadge evidence={i.evidence} />
            <span className="text-xs text-ink-3">Sources: {i.source_refs.length ? i.source_refs.join("; ") : "none attached"}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Cell({ items }: { items: string[] }) {
  return (
    <ul className="m-0 list-disc ps-4 text-xs text-ink-2">
      {items.map((x) => (
        <li key={x}>{x}</li>
      ))}
    </ul>
  );
}

/** Scenario comparison for one unit: columns are scenarios, rows are the quantities to compare. */
export function ScenarioCompare({ ev, interventions }: { ev: PolygonEvaluation; interventions: RestorationFeature["properties"]["interventions"] }) {
  const scs = ev.scenarios;
  if (scs.length === 0) {
    return (
      <p className="m-0 rounded-sm border border-dashed border-line-strong p-3 text-sm text-ink-2">
        No scenario is offered for this unit: Model 2 classes it as not feasible to restore. The limiting factors above say why.
      </p>
    );
  }
  const max = Math.max(...scs.map((s) => s.scenario.water_requirement_m3_ha_yr.high));
  const nameOf = (id: string) => interventions.find((i) => i.id === id)?.name ?? id.replace(/^iv-/, "").replace(/-/g, " ");
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scenario comparison (scrollable table)">
      <table className="data-table min-w-[34rem]">
        <caption className="visually-hidden">Restoration scenarios compared for one land unit. All values are simulated.</caption>
        <thead>
          <tr>
            <th scope="col">Compare</th>
            {scs.map((s) => (
              <th key={s.scenario.id} scope="col" className="!normal-case !tracking-normal">
                <span className="block text-sm text-ink">{s.scenario.name.split(":")[0]}</span>
                <span className="block text-xs font-normal text-ink-3">{s.viable ? "Viable under your constraints" : "Not viable under your constraints"}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-xs">Simulated class</th>
            {scs.map((s) => (
              <td key={s.scenario.id}>
                <span className="flex items-center gap-2">
                  <ClassSwatch code={s.scenario.post_class_code} size="sm" />
                  <span className="text-xs text-ink">{SUITABILITY_CLASSES[s.scenario.post_class_code].short}</span>
                </span>
                <span className="mt-1 block text-xs text-ink-3">probability {fmtNum(s.scenario.post_class_probability, 2, 2)}</span>
                <span className="mt-1 block"><EvidenceBadge evidence="simulated" /></span>
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-xs">Water requirement</th>
            {scs.map((s) => (
              <td key={s.scenario.id} className="min-w-36">
                <WaterRange w={s.scenario.water_requirement_m3_ha_yr} max={max} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-xs">Time to effect</th>
            {scs.map((s) => (
              <td key={s.scenario.id} className="text-xs text-ink-2 tnum">
                {s.scenario.time_to_effect_years.low}&ndash;{s.scenario.time_to_effect_years.high} years
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-xs">Interventions</th>
            {scs.map((s) => (
              <td key={s.scenario.id}>
                <Cell items={s.scenario.intervention_ids.map(nameOf)} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-xs">Water sources</th>
            {scs.map((s) => (
              <td key={s.scenario.id}>
                <Cell items={s.scenario.water_sources} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-xs">Infrastructure</th>
            {scs.map((s) => (
              <td key={s.scenario.id}>
                <Cell items={s.scenario.infrastructure} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-xs">Crop categories</th>
            {scs.map((s) => (
              <td key={s.scenario.id}>
                <Cell items={s.scenario.crop_categories} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-xs">Residual risks</th>
            {scs.map((s) => (
              <td key={s.scenario.id}>
                <Cell items={s.scenario.residual_risks} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="!px-3 !py-2 !text-xs">Constraint check</th>
            {scs.map((s) => (
              <td key={s.scenario.id} className="text-xs">
                {s.viable ? <span className="text-ok">Meets all constraints</span> : <Cell items={s.reasons} />}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/** Current (Model 1) vs simulated post-restoration area by class; the simulated column is labelled everywhere it appears. */
export function OutcomeComparison({ out }: { out: Outcome }) {
  const codes = [1, 2, 3, 4, 5] as SuitabilityClassCode[];
  const bar = (vals: Record<SuitabilityClassCode, number>, label: string) => (
    <div>
      <p className="m-0 mb-1 text-xs font-semibold text-ink-2">{label}</p>
      <div
        role="img"
        aria-label={`${label}: ${codes.filter((c) => vals[c] > 0).map((c) => `class ${c} ${fmtHa(vals[c])} hectares`).join(", ")}`}
        className="flex h-5 overflow-hidden rounded-xs border border-line-strong"
      >
        {codes.map((c) =>
          vals[c] > 0 ? (
            <span
              key={c}
              style={{ inlineSize: `${(vals[c] / Math.max(out.total_ha, 1e-9)) * 100}%`, background: SUITABILITY_CLASSES[c].color }}
              className={label.startsWith("Simulated") ? "bg-[length:6px_6px]" : undefined}
            />
          ) : null,
        )}
      </div>
    </div>
  );
  return (
    <div className="grid gap-3">
      {bar(out.before, "Current (Model 1)")}
      {bar(out.after, "Simulated after restoration (not observed)")}
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Current versus simulated area (scrollable table)">
      <table className="data-table">
        <caption className="visually-hidden">Hectares and dunums per suitability class, current versus simulated after restoration</caption>
        <thead>
          <tr>
            <th scope="col">Class</th>
            <th scope="col" className="num">Current ha</th>
            <th scope="col" className="num">Simulated ha</th>
            <th scope="col" className="num">Simulated dunum</th>
          </tr>
        </thead>
        <tbody>
          {CLASS_LIST.filter((c) => c.code !== 5 || out.before[5] > 0 || out.after[5] > 0).map((c) => (
            <tr key={c.code}>
              <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-sm !normal-case !tracking-normal !text-ink">
                <span className="flex items-center gap-2">
                  <ClassSwatch code={c.code} size="sm" />
                  {c.short}
                </span>
              </th>
              <td className="num">{fmtHa(out.before[c.code])}</td>
              <td className="num">{fmtHa(out.after[c.code])}</td>
              <td className="num">{fmtDunum(out.after[c.code])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}

const WATER_LIMITS = [null, 3000, 5000, 8000, 12000] as const;
const YEARS = [3, 5, 8, 10, 15];

export function ConstraintsForm({
  value,
  onChange,
  waterSources,
  tiers,
  preference,
  onPreference,
  idPrefix,
}: {
  value: RestorationConstraints;
  onChange: (c: RestorationConstraints) => void;
  waterSources: string[];
  tiers: { key: string; label: string }[];
  preference: string;
  onPreference: (p: string) => void;
  idPrefix: string;
}) {
  const toggleSource = (s: string, on: boolean) => {
    const set = new Set(value.allowed_water_sources);
    if (on) set.add(s);
    else set.delete(s);
    onChange({ ...value, allowed_water_sources: [...set] });
  };
  return (
    <div className="grid gap-3">
      <div>
        <FieldLabel htmlFor={`${idPrefix}-water`} hint="Scenarios whose central need is higher are marked not viable.">
          Maximum water available
        </FieldLabel>
        <select
          id={`${idPrefix}-water`}
          className="field"
          value={value.max_water_m3_ha_yr ?? ""}
          onChange={(e) => onChange({ ...value, max_water_m3_ha_yr: e.target.value === "" ? null : Number(e.target.value) })}
        >
          {WATER_LIMITS.map((w) => (
            <option key={String(w)} value={w ?? ""}>
              {w === null ? "No limit" : `${fmtNum(w, 0)} m³/ha/yr`}
            </option>
          ))}
        </select>
      </div>
      <fieldset className="m-0 min-w-0 border-0 p-0">
        <legend className="mb-1 text-sm font-semibold text-ink">Water sources you can use</legend>
        {waterSources.map((s, i) => (
          <CheckRow key={s} id={`${idPrefix}-src-${i}`} checked={value.allowed_water_sources.includes(s)} onChange={(on) => toggleSource(s, on)}>
            {s}
          </CheckRow>
        ))}
      </fieldset>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <FieldLabel htmlFor={`${idPrefix}-years`}>Time horizon</FieldLabel>
          <select id={`${idPrefix}-years`} className="field" value={value.max_years} onChange={(e) => onChange({ ...value, max_years: Number(e.target.value) })}>
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y} years
              </option>
            ))}
          </select>
        </div>
        <div>
          <FieldLabel htmlFor={`${idPrefix}-feas`}>Min. feasibility</FieldLabel>
          <select
            id={`${idPrefix}-feas`}
            className="field"
            value={value.min_feasibility}
            onChange={(e) => onChange({ ...value, min_feasibility: e.target.value as FeasibilityClass })}
          >
            {FEASIBILITY_ORDER.map((k) => (
              <option key={k} value={k}>
                {k === "not_feasible" ? "Any" : FEASIBILITY_META[k].label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <CheckRow id={`${idPrefix}-irrev`} checked={value.exclude_irreversible} onChange={(on) => onChange({ ...value, exclude_irreversible: on })}>
        <span>Exclude units with a severe irreversible limit</span>
      </CheckRow>
      <div>
        <FieldLabel htmlFor={`${idPrefix}-pref`} hint="Which scenario is used for the current-vs-simulated comparison and exports.">
          Scenario shown
        </FieldLabel>
        <select id={`${idPrefix}-pref`} className="field" value={preference} onChange={(e) => onPreference(e.target.value)}>
          <option value="best">Best viable scenario per unit</option>
          {tiers.map((t) => (
            <option key={t.key} value={t.key}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

export function tiersFrom(features: RestorationFeature[]): { key: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const f of features) for (const s of f.properties.scenarios) if (!seen.has(scenarioKey(s))) seen.set(scenarioKey(s), s.name.split(":")[0] ?? s.name);
  return [...seen.entries()].map(([key, label]) => ({ key, label }));
}
