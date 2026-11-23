/**
 * Export builders (pure). Every demo export carries the DEMONSTRATION DATA marker:
 *  - GeoJSON: top-level foreign members `demonstration_data` + `notice`, and `demonstration_data: true` on every feature.
 *  - CSV: first line is a `#` comment with the notice, plus a `demonstration_data` column.
 *  - JSON summary: `demonstration_data` + `notice` fields.
 *  - HTML report: banner at the top of every printed page.
 */
import type { RestorationFeature, SuitabilityCollection, SuitabilityFeature } from "./contract";
import { EVIDENCE_META, FEASIBILITY_META, SUITABILITY_CLASSES, factorLabel } from "./classes";
import { chooseScenario, evaluateRun, scenarioKey, summariseOutcome, type PolygonEvaluation } from "./restoration";
import type { RestorationConstraints, RestorationRun, SuitabilityRun } from "./types";
import { DEMO_NOTICE } from "./demo/notice";
import { DUNUM_DEFINITION } from "./units";

export interface ExportOptions {
  demo: boolean;
  generatedAt?: string;
}

const stamp = (o: ExportOptions): string => o.generatedAt ?? new Date().toISOString();

export function csvEscape(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows: unknown[][], demo: boolean, extraComments: string[] = []): string {
  const lines: string[] = [];
  if (demo) lines.push(`# ${DEMO_NOTICE}`);
  for (const c of extraComments) lines.push(`# ${c}`);
  for (const row of rows) lines.push(row.map(csvEscape).join(","));
  return lines.join("\r\n") + "\r\n";
}

/* ------------------------------------------------------------------ suitability */

export function buildSuitabilityGeoJSON(fc: SuitabilityCollection, regionId: string, o: ExportOptions): string {
  const out = {
    type: "FeatureCollection",
    ...(o.demo ? { demonstration_data: true, notice: DEMO_NOTICE } : {}),
    name: `green-nova-suitability-${regionId}`,
    generated_at: stamp(o),
    area_units: { area_ha: "hectare", area_dunum: DUNUM_DEFINITION },
    features: fc.features.map((f) => ({
      ...f,
      properties: { ...f.properties, ...(o.demo ? { demonstration_data: true } : {}) },
    })),
  };
  return JSON.stringify(out, null, 1);
}

const limitingNames = (f: SuitabilityFeature): string =>
  f.properties.factors
    .filter((x) => x.status === "limiting" || x.status === "restricted")
    .map((x) => factorLabel(x.name))
    .join("; ");

export function buildSuitabilityCSV(fc: SuitabilityCollection, regionId: string, o: ExportOptions): string {
  const header = [
    "id",
    "class_code",
    "class_label",
    "area_ha",
    "area_dunum",
    "confidence",
    "confidence_method",
    "centroid_lon",
    "centroid_lat",
    "effective_resolution_m",
    "limiting_or_restricted_factors",
    "model_version",
    "demonstration_data",
  ];
  const rows: unknown[][] = [header];
  for (const f of fc.features) {
    const p = f.properties;
    rows.push([
      p.id,
      p.class_code,
      p.class_label,
      p.area_ha,
      p.area_dunum,
      p.confidence,
      p.confidence_method,
      p.centroid[0],
      p.centroid[1],
      p.effective_resolution_m,
      limitingNames(f),
      p.provenance.model_version,
      o.demo ? "TRUE" : "FALSE",
    ]);
  }
  return toCsv(rows, o.demo, [`region ${regionId}`, DUNUM_DEFINITION, `generated ${stamp(o)}`]);
}

export function buildSuitabilitySummaryJSON(run: SuitabilityRun, o: ExportOptions): string {
  return JSON.stringify(
    {
      ...(o.demo ? { demonstration_data: true, notice: DEMO_NOTICE } : {}),
      region_id: run.region_id,
      generated_at: stamp(o),
      area_units: { area_ha: "hectare", area_dunum: DUNUM_DEFINITION },
      polygon_count: run.polygon_count,
      total_area_ha: run.total_area_ha,
      total_area_dunum: run.total_area_dunum,
      per_class: Object.fromEntries(
        run.stats.map((s) => [String(s.code), { label: s.label, polygon_count: s.polygon_count, area_ha: s.area_ha, area_dunum: s.area_dunum, share: s.share }]),
      ),
      run_metadata: run.metadata,
    },
    null,
    1,
  );
}

/* ------------------------------------------------------------------ restoration */

function chosenFor(ev: PolygonEvaluation, preference: string) {
  return chooseScenario(ev, preference);
}

export function buildRestorationGeoJSON(run: RestorationRun, c: RestorationConstraints, preference: string, o: ExportOptions): string {
  const evals = evaluateRun(run.features, c);
  const out = {
    type: "FeatureCollection",
    ...(o.demo ? { demonstration_data: true, notice: DEMO_NOTICE } : {}),
    name: `green-nova-restoration-${run.region_id}`,
    generated_at: stamp(o),
    constraints: c,
    scenario_preference: preference,
    simulated_outcomes: "Post-restoration classes, water ranges and times are SIMULATED scenario outputs, never observed results.",
    features: evals.map((ev) => {
      const ch = chosenFor(ev, preference);
      return {
        ...ev.feature,
        properties: {
          ...ev.feature.properties,
          ...(o.demo ? { demonstration_data: true } : {}),
          constraint_exclusions: ev.excludedReasons,
          selected_scenario_id: ch?.id ?? null,
        },
      };
    }),
  };
  return JSON.stringify(out, null, 1);
}

export function buildRestorationCSV(run: RestorationRun, c: RestorationConstraints, preference: string, o: ExportOptions): string {
  const header = [
    "id",
    "source_polygon_id",
    "current_class_code",
    "area_ha",
    "area_dunum",
    "feasibility_class",
    "feasibility_score",
    "feasibility_interval_lo",
    "feasibility_interval_hi",
    "feasibility_confidence",
    "limiting_factors",
    "excluded_by_constraints",
    "scenario",
    "simulated_post_class_code",
    "simulated_post_class_probability",
    "water_m3_ha_yr_low",
    "water_m3_ha_yr_central",
    "water_m3_ha_yr_high",
    "time_to_effect_years_low",
    "time_to_effect_years_high",
    "scenario_evidence",
    "demonstration_data",
  ];
  const rows: unknown[][] = [header];
  for (const ev of evaluateRun(run.features, c)) {
    const p = ev.feature.properties;
    const ch = chosenFor(ev, preference);
    rows.push([
      p.id,
      p.source_polygon_id,
      p.current_class_code,
      p.area_ha,
      p.area_dunum,
      p.feasibility.class,
      p.feasibility.score,
      p.feasibility.interval[0],
      p.feasibility.interval[1],
      p.feasibility.confidence,
      p.limiting_factors.map((l) => `${factorLabel(l.factor)} (${l.reversibility}, severity ${l.severity})`).join("; "),
      ev.excludedReasons.join(" | "),
      ch?.name ?? "",
      ch?.post_class_code ?? "",
      ch?.post_class_probability ?? "",
      ch?.water_requirement_m3_ha_yr.low ?? "",
      ch?.water_requirement_m3_ha_yr.central ?? "",
      ch?.water_requirement_m3_ha_yr.high ?? "",
      ch?.time_to_effect_years.low ?? "",
      ch?.time_to_effect_years.high ?? "",
      ch ? "simulated" : "",
      o.demo ? "TRUE" : "FALSE",
    ]);
  }
  return toCsv(rows, o.demo, [
    `region ${run.region_id}; job ${run.job_id}`,
    DUNUM_DEFINITION,
    "Scenario columns are SIMULATED outputs, never observed restoration results.",
    `generated ${stamp(o)}`,
  ]);
}

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch] as string);

const num = (v: number, d = 1): string => v.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: d });

/** Standalone, printable HTML report (Print > Save as PDF gives a PDF). */
export function buildRestorationReportHTML(run: RestorationRun, c: RestorationConstraints, preference: string, o: ExportOptions): string {
  const evals = evaluateRun(run.features, c);
  const out = summariseOutcome(evals, preference);
  const classes = [1, 2, 3, 4, 5] as const;
  const banner = o.demo ? `<div class="demo" role="note"><strong>${esc(DEMO_NOTICE)}</strong><br>Synthetic records generated locally. No model produced them. Scenario outcomes are simulated by design.</div>` : "";
  const rows = evals
    .map((ev) => {
      const p = ev.feature.properties;
      const ch = chosenFor(ev, preference);
      return `<tr>
<td>${esc(p.source_polygon_id)}</td><td>${p.current_class_code}</td>
<td class="n">${num(p.area_ha)}<br><span class="muted">${num(p.area_dunum)} dunum</span></td>
<td>${esc(FEASIBILITY_META[p.feasibility.class].label)}<br><span class="muted">score ${p.feasibility.score} (${p.feasibility.interval[0]}–${p.feasibility.interval[1]})</span></td>
<td>${p.limiting_factors.map((l) => `${esc(factorLabel(l.factor))} <span class="muted">(${esc(l.reversibility.replace("_", " "))})</span>`).join("<br>") || "—"}</td>
<td>${ch ? `${esc(ch.name)}<br><span class="muted">simulated class ${ch.post_class_code}, p=${ch.post_class_probability}</span>` : ev.excludedReasons.length ? `<span class="muted">Excluded: ${esc(ev.excludedReasons[0])}</span>` : `<span class="muted">No viable scenario under the constraints</span>`}</td>
<td class="n">${ch ? `${num(ch.water_requirement_m3_ha_yr.low, 0)}–${num(ch.water_requirement_m3_ha_yr.high, 0)}<br><span class="muted">central ${num(ch.water_requirement_m3_ha_yr.central, 0)}</span>` : "—"}</td>
</tr>`;
    })
    .join("\n");
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GREEN NOVA AI – Restoration potential report (${esc(run.region_id)})</title>
<style>
:root{color-scheme:light}
body{font:14px/1.5 system-ui,Segoe UI,Arial,sans-serif;margin:0;color:#161c18;background:#f5f2ea}
main{max-width:1000px;margin:0 auto;padding:24px}
h1{font-size:24px;margin:.2em 0}h2{font-size:17px;margin:1.6em 0 .4em;border-bottom:1px solid #8a8f84;padding-bottom:4px}
.demo{border:2px solid #161c18;background:#e8d9a8;padding:10px 14px;margin:0 0 16px;font-size:14px}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{border-bottom:1px solid #cfc9b9;padding:6px 8px;text-align:start;vertical-align:top}
th{background:#ebe6da}td.n{white-space:nowrap}.muted{color:#4b534d}
.note{background:#fbf9f4;border:1px solid #cfc9b9;padding:10px 14px}
@media print{body{background:#fff}.demo{position:running(demo)}@page{margin:14mm}}
</style></head><body><main>
${banner}
<h1>Restoration potential report</h1>
<p class="muted">GREEN NOVA AI · region <code>${esc(run.region_id)}</code> · job <code>${esc(run.job_id)}</code> · generated ${esc(stamp(o))}</p>
<h2>Scope and constraints</h2>
<p>${out.counts.analysed} suitability units analysed (${num(out.total_ha)} ha · ${num(out.total_ha * 10)} dunum). ${esc(DUNUM_DEFINITION)}.</p>
<ul>
<li>Maximum central water need: ${c.max_water_m3_ha_yr == null ? "not limited" : num(c.max_water_m3_ha_yr, 0) + " m³/ha/yr"}</li>
<li>Available water sources: ${c.allowed_water_sources.length ? esc(c.allowed_water_sources.join(", ")) : "none selected"}</li>
<li>Time horizon: up to ${c.max_years} years · minimum feasibility: ${esc(FEASIBILITY_META[c.min_feasibility].label)} · exclude severe irreversible limits: ${c.exclude_irreversible ? "yes" : "no"}</li>
<li>Scenario selection: ${esc(preference === "best" ? "best viable scenario per unit" : preference)}</li>
</ul>
<h2>Current vs simulated post-restoration suitability (hectares)</h2>
<table><thead><tr><th>Class</th><th>Current (Model 1)</th><th>Simulated after restoration</th></tr></thead><tbody>
${classes.map((k) => `<tr><td>${k} – ${esc(SUITABILITY_CLASSES[k].label)}</td><td class="n">${num(out.before[k])}</td><td class="n">${num(out.after[k])}</td></tr>`).join("\n")}
</tbody></table>
<p>Units with a viable scenario: ${out.counts.with_scenario} · excluded by constraints: ${out.counts.excluded} · no viable scenario: ${out.counts.no_viable_scenario}.<br>
Aggregate water need of the chosen scenarios: ${num(out.water_mm3_yr.low, 2)}–${num(out.water_mm3_yr.high, 2)} million m³/yr (central ${num(out.water_mm3_yr.central, 2)}).</p>
<h2>Units</h2>
<table><thead><tr><th>Unit</th><th>Class</th><th>Area (ha)</th><th>Feasibility</th><th>Limiting factors</th><th>Selected scenario (simulated)</th><th>Water m³/ha/yr</th></tr></thead><tbody>
${rows}
</tbody></table>
<h2>How to read this report</h2>
<div class="note"><p><strong>Evidence classes.</strong> ${(["observed", "ml_predicted", "expert_rule", "simulated"] as const).map((e) => `<em>${esc(EVIDENCE_META[e].label)}</em>: ${esc(EVIDENCE_META[e].definition)}`).join(" ")}</p>
<p><strong>Limitations.</strong> Post-restoration classes, water requirement ranges and times to effect are simulated scenario outputs with ranges, never observed restoration results. Feasibility intervals express model uncertainty and are not guarantees. Spatial precision is limited by the coarsest input that drives each decision. Field verification is required before any investment.</p></div>
</main></body></html>`;
}

/** Re-exported for tests / UI. */
export { scenarioKey };
export type { RestorationFeature };
