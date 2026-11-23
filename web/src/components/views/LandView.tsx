"use client";

import Link from "next/link";
import { useMemo, type ReactNode } from "react";
import { MapView } from "@/components/map";
import { BasemapNote } from "@/components/data/BasemapNote";
import { Model2Caveats } from "@/components/data/Model2Caveats";
import { FactorList } from "@/components/data/FactorList";
import { ProbabilityBars } from "@/components/data/PolygonDetail";
import { FeasibilityChip, InterventionList, LimitingFactorList, ScenarioCompare } from "@/components/data/RestorationParts";
import { ClassChip, EvidenceBadge, KV, Meter, Skeleton } from "@/components/ui/primitives";
import { DemoNote, EmptyState, ErrorState } from "@/components/ui/states";
import { CLASS5_NOTE, CONFIDENCE_EXPLAINER } from "@/lib/classes";
import type { Evidence, MeasuredValue, SuitabilityFactor } from "@/lib/contract";
import { fmtConfidence, fmtDunum, fmtHa, fmtNum } from "@/lib/format";
import { formatLatLon, formatLatLonDms, geometryBBox } from "@/lib/geo";
import { useAsync, useProvider } from "@/lib/hooks";
import { currentUnits } from "@/lib/layers";
import { limitationsFor, recommendationsFor } from "@/lib/recommend";
import { DEFAULT_CONSTRAINTS, availableWaterSources, evaluatePolygon } from "@/lib/restoration";
import { DUNUM_DEFINITION } from "@/lib/units";
import { ProviderError } from "@/lib/types";

const isMeasured = (v: unknown): v is MeasuredValue => typeof v === "object" && v !== null && "value" in v && "unit" in v;

function unc(u: MeasuredValue["uncertainty"]): string {
  if (u === undefined) return "";
  if (typeof u === "number") return `±${fmtNum(u, 2)}`;
  if (Array.isArray(u)) return `${fmtNum(u[0], 2)} to ${fmtNum(u[1], 2)}`;
  return Object.entries(u)
    .map(([k, v]) => `${k} ${fmtNum(v, 2)}`)
    .join(", ");
}

interface Row {
  label: string;
  value: string;
  evidence: Evidence;
  uncertainty?: string;
  note?: string;
}

function ValueTable({ rows, caption }: { rows: Row[]; caption: string }) {
  if (rows.length === 0) return <p className="m-0 text-sm text-ink-2">No values are available for this section.</p>;
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={`${caption} (scrollable)`}>
      <table className="data-table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Property</th>
            <th scope="col" className="num">Value</th>
            <th scope="col">Uncertainty</th>
            <th scope="col">Evidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-sm !normal-case !tracking-normal !font-medium !text-ink">
                {r.label}
              </th>
              <td className="num">{r.value}</td>
              <td className="text-ink-3">{r.uncertainty || "not stated"}</td>
              <td>
                <EvidenceBadge evidence={r.evidence} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SOIL_LABEL: Record<string, string> = {
  ph: "pH",
  ec_ds_m: "Electrical conductivity (salinity)",
  soc_pct: "Soil organic carbon",
  sand_pct: "Sand",
  silt_pct: "Silt",
  clay_pct: "Clay",
  depth_cm: "Soil depth",
};

function factorRow(f: SuitabilityFactor, label: string): Row {
  return { label, value: f.value === null ? "n/a" : typeof f.value === "number" ? `${fmtNum(f.value, 2)}${f.unit ? ` ${f.unit}` : ""}` : f.value, evidence: f.evidence };
}

function Section({ id, title, children, hint }: { id: string; title: string; children: ReactNode; hint?: string }) {
  return (
    <section aria-labelledby={id} className="border-t border-line pt-6">
      <h2 id={id} className="h-panel !text-lg">
        {title}
      </h2>
      {hint ? <p className="mt-1 text-xs text-ink-3">{hint}</p> : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function LandView({ id }: { id: string }) {
  const provider = useProvider();
  const detail = useAsync(() => provider.getLandDetail(id), [provider, id]);
  const d = detail.status === "success" ? detail.data : null;
  const f = d?.suitability ?? null;
  const r = d?.restoration ?? null;

  const rows = useMemo(() => {
    if (!f) return { soil: [] as Row[], terrain: [] as Row[], water: [] as Row[] };
    const p = f.properties;
    const fac = (n: string) => p.factors.find((x) => x.name === n);
    const soil: Row[] = [];
    if (r) {
      for (const [k, v] of Object.entries(r.properties.soil)) soil.push({ label: SOIL_LABEL[k] ?? k, value: `${fmtNum(v.value, 2)}${v.unit ? ` ${v.unit}` : ""}`, evidence: v.evidence, uncertainty: unc(v.uncertainty) });
    } else {
      for (const [n, label] of [["soil_ph", "pH"], ["soil_salinity_ec", "Electrical conductivity (salinity)"], ["soil_organic_carbon", "Soil organic carbon"], ["soil_depth", "Soil depth"], ["sand_fraction", "Sand"]] as const) {
        const x = fac(n);
        if (x) soil.push(factorRow(x, label));
      }
    }
    const terrain: Row[] = [];
    if (r) {
      const t = r.properties.terrain;
      for (const [k, label] of [["elevation_m", "Elevation"], ["slope_deg", "Slope"]] as const) {
        const v = t[k];
        if (isMeasured(v)) terrain.push({ label, value: `${fmtNum(v.value, 1)} ${v.unit}`, evidence: v.evidence, uncertainty: unc(v.uncertainty) });
        else if (typeof v === "number") terrain.push({ label, value: fmtNum(v, 1), evidence: "observed" });
      }
      if (t.erosion_risk) terrain.push({ label: "Erosion risk", value: String(t.erosion_risk.value), evidence: t.erosion_risk.evidence });
    } else {
      const s = fac("slope");
      if (s) terrain.push(factorRow(s, "Slope"));
    }
    const water: Row[] = [];
    const rain = r?.properties.climate.rainfall_mm_yr;
    if (isMeasured(rain)) water.push({ label: "Annual rainfall", value: `${fmtNum(rain.value, 0)} ${rain.unit}`, evidence: rain.evidence, uncertainty: unc(rain.uncertainty) });
    else if (fac("rainfall")) water.push(factorRow(fac("rainfall")!, "Annual rainfall"));
    const wa = fac("water_availability");
    if (wa) water.push(factorRow(wa, "Water availability index"));
    const temp = r?.properties.climate.temp_mean_c;
    if (isMeasured(temp)) water.push({ label: "Mean temperature", value: `${fmtNum(temp.value, 1)} ${temp.unit}`, evidence: temp.evidence, uncertainty: unc(temp.uncertainty) });
    return { soil, terrain, water };
  }, [f, r]);

  const limitations = f ? limitationsFor(f) : [];
  const recommendations = f ? recommendationsFor(f, r) : [];
  const ev = r ? evaluatePolygon(r, { ...DEFAULT_CONSTRAINTS, min_feasibility: "not_feasible", allowed_water_sources: availableWaterSources([r]) }) : null;

  if (detail.status === "error") {
    const notFound = detail.error instanceof ProviderError && detail.error.code === "not_found";
    return (
      <main id="main" tabIndex={-1} className="mx-auto grid max-w-3xl gap-4 px-[var(--spacing-gutter)] py-10 outline-none">
        <h1 className="h-page">{notFound ? "Land unit not found" : "Could not load this land unit"}</h1>
        {notFound ? (
          <EmptyState title="No such land unit" action={<Link href="/suitability" className="btn btn-primary no-underline">Open the suitability workspace</Link>}>
            {detail.error.message}
          </EmptyState>
        ) : (
          <ErrorState message={detail.error.message} onRetry={detail.reload} />
        )}
      </main>
    );
  }

  const p = f?.properties;
  const [lon, lat] = p?.centroid ?? [0, 0];
  const regionId = id.replace(/^m1-/, "").replace(/-\d+$/, "");

  return (
    <main id="main" tabIndex={-1} className="mx-auto grid max-w-7xl gap-8 px-[var(--spacing-gutter)] py-8 outline-none lg:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="grid min-w-0 content-start gap-6">
        <header className="grid gap-3">
          <nav aria-label="Breadcrumb" className="text-xs text-ink-3">
            <ol className="m-0 flex flex-wrap items-center gap-1.5 p-0">
              <li className="list-none"><Link href="/dashboard" className="text-ink-2">Dashboard</Link></li>
              <li className="list-none" aria-hidden="true">/</li>
              <li className="list-none"><Link href={`/suitability?region=${regionId}`} className="text-ink-2">Suitability</Link></li>
              <li className="list-none" aria-hidden="true">/</li>
              <li className="list-none" aria-current="page">Land unit</li>
            </ol>
          </nav>
          <h1 className="h-page">
            Land unit <span className="break-all font-mono text-[0.85em] font-medium">{id}</span>
          </h1>
          {p ? (
            <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-2">
              <ClassChip code={p.class_code} />
              <span className="text-sm text-ink-2 tnum">
                {fmtHa(p.area_ha)} ha &middot; {fmtDunum(p.area_dunum)} dunum
              </span>
            </p>
          ) : (
            <Skeleton className="h-6 w-72" />
          )}
          <DemoNote />
        </header>

        {detail.status === "loading" ? (
          <div className="grid gap-4" role="status" aria-label="Loading land unit">
            <Skeleton className="h-40" />
            <Skeleton className="h-56" />
            <Skeleton className="h-40" />
          </div>
        ) : null}

        {f && p ? (
          <>
            <Section id="l-overview" title="Location, area and current suitability">
              <dl className="m-0">
                <KV k="Coordinates">
                  <span className="block font-mono text-sm">{formatLatLon(lon, lat, 5)}</span>
                  <span className="block font-mono text-xs text-ink-3">{formatLatLonDms(lon, lat)}</span>
                  <span className="block text-xs text-ink-3">Centroid, WGS 84 (EPSG:4326)</span>
                </KV>
                <KV k="Area">
                  <span className="tnum">{fmtHa(p.area_ha)} ha &middot; {fmtDunum(p.area_dunum)} dunum</span>
                  <span className="block text-xs text-ink-3">{DUNUM_DEFINITION}. Area is computed in an equal-area projection.</span>
                </KV>
                <KV k="Current suitability">
                  <ClassChip code={p.class_code} />
                  {p.class_code === 5 ? <span className="mt-1 block text-xs text-ink-2">{CLASS5_NOTE}</span> : null}
                </KV>
                <KV k="Model confidence">
                  <span className="flex items-center gap-3">
                    <span className="w-10 font-semibold tnum">{fmtConfidence(p.confidence)}</span>
                    <Meter value={p.confidence} label="Confidence" className="max-w-56 flex-1" />
                  </span>
                  <span className="mt-1 block text-xs text-ink-2">{p.confidence_method}</span>
                  <span className="mt-1 block text-xs text-ink-3">{CONFIDENCE_EXPLAINER}</span>
                </KV>
                <KV k="Effective resolution">
                  <span className="tnum">{p.effective_resolution_m} m</span>
                </KV>
                <KV k="Provenance">
                  <span className="font-mono text-xs">{p.provenance.model_version}</span>
                  <span className="block text-xs text-ink-3">Sources: {p.provenance.data_sources.join("; ")}</span>
                </KV>
              </dl>
              <h3 className="h-panel mb-2 mt-5">Class probabilities</h3>
              <div className="max-w-md">
                <ProbabilityBars probs={p.class_probabilities} />
              </div>
            </Section>

            <Section id="l-factors" title="Factors behind the class" hint="Each factor carries a status and an evidence class: observed, ML-predicted, expert rule or simulated.">
              <FactorList factors={p.factors} />
            </Section>

            <Section id="l-soil" title="Soil characteristics">
              <ValueTable rows={rows.soil} caption="Soil characteristics with evidence class and uncertainty" />
            </Section>
            <Section id="l-terrain" title="Terrain">
              <ValueTable rows={rows.terrain} caption="Terrain characteristics" />
            </Section>
            <Section id="l-water" title="Water indicators">
              <ValueTable rows={rows.water} caption="Water and climate indicators" />
            </Section>

            <Section id="l-restoration" title="Restoration potential" hint="Model 2. Applies to class 3 and 4 land. Outcomes are simulated scenarios, never observed results.">
              {r && ev ? (
                <div className="grid gap-5">
                  <Model2Caveats />
                  <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-2">
                    Feasibility <FeasibilityChip cls={r.properties.feasibility.class} /> score <span className="tnum">{r.properties.feasibility.score}</span>, interval{" "}
                    <span className="tnum">{r.properties.feasibility.interval[0]}&ndash;{r.properties.feasibility.interval[1]}</span>, confidence <span className="tnum">{r.properties.feasibility.confidence}</span>
                  </p>
                  <div>
                    <h3 className="h-panel mb-1">What prevents cultivation</h3>
                    <LimitingFactorList factors={r.properties.limiting_factors} />
                  </div>
                  <div>
                    <h3 className="h-panel mb-1">Interventions</h3>
                    <InterventionList interventions={r.properties.interventions} />
                  </div>
                  <div>
                    <h3 className="h-panel mb-1">Scenarios</h3>
                    <ScenarioCompare ev={ev} interventions={r.properties.interventions} />
                  </div>
                  <p className="m-0 text-xs text-ink-3">
                    <Link href={`/restoration?region=${regionId}`}>Compare scenarios under your own constraints on the Restoration page.</Link>
                  </p>
                </div>
              ) : (
                <EmptyState title="Not analysed for restoration">{d?.restoration_note ?? "No restoration result exists for this unit."}</EmptyState>
              )}
            </Section>

            <Section id="l-limits" title="Limitations" hint="Rule-based statements derived from this record. Evidence: expert rule.">
              <ul className="m-0 grid list-none gap-2 p-0">
                {limitations.map((s) => (
                  <li key={s.text} className="flex items-start gap-3 text-sm text-ink-2">
                    <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-ink-3" />
                    <span>{s.text}</span>
                  </li>
                ))}
              </ul>
            </Section>

            <Section id="l-reco" title="Recommendations" hint="Rule-based, not a model output. Always verify in the field.">
              <ul className="m-0 grid list-none gap-2 p-0">
                {recommendations.map((s) => (
                  <li key={s.text} className="flex items-start gap-3 text-sm text-ink-2">
                    <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" />
                    <span>{s.text}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-3">
                <EvidenceBadge evidence="expert_rule" />
              </div>
            </Section>
          </>
        ) : null}
      </div>

      <aside aria-label="Location" className="grid content-start gap-4 lg:sticky lg:top-[calc(var(--demo-h)+var(--app-h)+1rem)] lg:self-start">
        <div className="h-72 overflow-hidden rounded-md border border-line lg:h-80">
          {f ? (
            <MapView
              className="size-full"
              interactive={false}
              ariaLabel={`Locator map showing land unit ${id}`}
              units={currentUnits({ type: "FeatureCollection", features: [f] }, new Set([id]))}
              selectedIds={[id]}
              fitTo={geometryBBox(f.geometry)}
              showControls={false}
            />
          ) : (
            <Skeleton className="size-full" />
          )}
        </div>
        <BasemapNote />
        {!provider.isDemo && f ? (
          <div className="grid gap-1.5 rounded-sm border border-line p-3">
            <p className="h-panel m-0">GeoTIFF clip of this unit</p>
            <a className="text-sm" href={`/api/gn/land/${encodeURIComponent(id)}/geotiff?layer=suitability`}>Suitability raster</a>
            {r ? <a className="text-sm" href={`/api/gn/land/${encodeURIComponent(id)}/geotiff?layer=feasibility`}>Restoration feasibility raster</a> : null}
            {r ? <a className="text-sm" href={`/api/gn/land/${encodeURIComponent(id)}/geotiff?layer=post_restoration`}>Post-restoration suitability raster (simulated)</a> : null}
          </div>
        ) : null}
        <Link href={`/suitability?region=${regionId}`} className="btn btn-secondary no-underline">
          Back to the suitability workspace
        </Link>
      </aside>
    </main>
  );
}
