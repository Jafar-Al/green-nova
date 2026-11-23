"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { MapView } from "@/components/map";
import { MapLegend } from "@/components/map/MapLegend";
import { AreaStats } from "@/components/data/AreaStats";
import { FilterPanel } from "@/components/data/FilterPanel";
import { PolygonDetail } from "@/components/data/PolygonDetail";
import { Model2Caveats } from "@/components/data/Model2Caveats";
import { RegionSelectors } from "@/components/data/RegionSelectors";
import { RunMetaNote } from "@/components/data/RunMetaNote";
import { Button, CheckRow, LinkButton, Segmented, Skeleton } from "@/components/ui/primitives";
import { DemoNote, EmptyState, ErrorState, OfflineBanner } from "@/components/ui/states";
import { IconArrowRight } from "@/components/ui/icons";
import { CLASS_LIST, FEASIBILITY_META } from "@/lib/classes";
import type { FeasibilityClass, SuitabilityClassCode } from "@/lib/contract";
import { fmtDateTime, fmtDunum, fmtHa, fmtInt } from "@/lib/format";
import { geometryBBox } from "@/lib/geo";
import { useProvider } from "@/lib/hooks";
import {
  defaultSuitabilityFilters,
  passesSuitabilityFilters,
  restorationLayerUnits,
  suitabilityUnits,
  type SuitabilityFilters,
} from "@/lib/layers";
import { DEFAULT_REGION, useRegionBundle, useRegionList, useRegionParam } from "@/lib/region-data";
import { DUNUM_DEFINITION } from "@/lib/units";

type Layer = "suitability" | "restoration";
const FEAS: FeasibilityClass[] = ["high", "moderate", "low", "not_feasible"];

function DashboardInner() {
  const provider = useProvider();
  const [regionId, setRegionId] = useRegionParam();
  const list = useRegionList(provider);
  const bundle = useRegionBundle(provider, regionId);
  const [layer, setLayer] = useState<Layer>("suitability");
  const [flt, setFlt] = useState<SuitabilityFilters>(defaultSuitabilityFilters);
  const [feas, setFeas] = useState<Set<FeasibilityClass>>(new Set(FEAS));
  const [confidenceOverlay, setConfidenceOverlay] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const data = bundle.status === "success" ? bundle.data : null;
  const polygons = data?.polygons ?? null;
  const regionInfo = list.data?.regions.find((r) => r.id === regionId);

  const units = useMemo(() => {
    if (!polygons) return null;
    return layer === "suitability"
      ? suitabilityUnits(polygons, flt, confidenceOverlay ? "confidence" : "class")
      : restorationLayerUnits(polygons, data?.restoration ?? null, feas);
  }, [polygons, layer, flt, feas, confidenceOverlay, data?.restoration]);

  const counts = useMemo(() => {
    const c: Partial<Record<SuitabilityClassCode, number>> = {};
    for (const f of polygons?.features ?? []) c[f.properties.class_code] = (c[f.properties.class_code] ?? 0) + 1;
    return c;
  }, [polygons]);
  const shown = useMemo(() => (polygons?.features ?? []).filter((f) => passesSuitabilityFilters(f, flt)).length, [polygons, flt]);

  const feasCounts = useMemo(() => {
    const out: Record<FeasibilityClass, { n: number; ha: number; dunum: number }> = {
      high: { n: 0, ha: 0, dunum: 0 },
      moderate: { n: 0, ha: 0, dunum: 0 },
      low: { n: 0, ha: 0, dunum: 0 },
      not_feasible: { n: 0, ha: 0, dunum: 0 },
    };
    for (const f of data?.restoration?.features ?? []) {
      const o = out[f.properties.feasibility.class];
      o.n += 1;
      o.ha += f.properties.area_ha;
      o.dunum += f.properties.area_dunum;
    }
    return out;
  }, [data?.restoration]);

  const selected = polygons?.features.find((f) => f.properties.id === selectedId) ?? null;
  const selectedRest = data?.restoration?.features.find((f) => f.properties.source_polygon_id === selectedId) ?? null;
  const fit = data ? geometryBBox(data.boundary.geometry) : null;

  const changeRegion = (id: string) => {
    setSelectedId(null);
    setRegionId(id);
  };

  return (
    <main
      id="main"
      tabIndex={-1}
      className="grid min-h-[calc(100dvh-var(--demo-h)-var(--app-h))] grid-cols-1 outline-none lg:h-[calc(100dvh-var(--demo-h)-var(--app-h))] lg:min-h-0 lg:grid-cols-[19.5rem_minmax(0,1fr)_23rem] lg:[grid-template-areas:'controls_map_side']"
    >
      <h1 className="visually-hidden">Intelligence dashboard</h1>

      {/* ---------------- map ---------------- */}
      <section aria-label="Satellite map" className="relative h-[62dvh] min-h-[24rem] lg:h-auto lg:min-h-0 lg:[grid-area:map]">
        <MapView
          className="size-full"
          ariaLabel={`Satellite map of ${regionInfo?.name ?? "the selected governorate"} with ${layer === "suitability" ? "land suitability" : "restoration feasibility"} overlay`}
          boundary={data?.boundary ?? null}
          units={units}
          selectedIds={selectedId ? [selectedId] : []}
          fitTo={fit}
          onSelect={(id) => setSelectedId((cur) => (cur === id ? null : id))}
          onBackgroundClick={() => setSelectedId(null)}
          getTooltip={(id) => {
            const f = polygons?.features.find((x) => x.properties.id === id);
            if (!f) return null;
            const p = f.properties;
            return `${p.id} · class ${p.class_code} · ${fmtHa(p.area_ha)} ha`;
          }}
          overlay={
            data?.run ? (
              layer === "suitability" ? (
                <MapLegend mode={confidenceOverlay ? "confidence" : "class"} counts={confidenceOverlay ? undefined : counts} />
              ) : (
                <MapLegend mode="restoration" counts={{ high: feasCounts.high.n, moderate: feasCounts.moderate.n, low: feasCounts.low.n, not_feasible: feasCounts.not_feasible.n }} />
              )
            ) : null
          }
        />
      </section>

      {/* ---------------- controls ---------------- */}
      <aside aria-label="Dashboard controls" className="grid grid-cols-[minmax(0,1fr)] content-start gap-5 border-t border-line p-4 lg:overflow-y-auto lg:border-e lg:border-t-0 lg:[grid-area:controls]">
        <div>
          <h2 className="h-page !text-[1.5rem]">Intelligence dashboard</h2>
          <p className="mt-1 text-sm text-ink-2">Satellite map with land suitability and restoration layers for a governorate.</p>
        </div>
        <OfflineBanner />
        <RegionSelectors list={list.data} regionId={regionId} onRegion={changeRegion} idPrefix="dash" loading={list.status === "loading"} />
        <Segmented<Layer>
          legend="Map layer"
          name="dash-layer"
          value={layer}
          onChange={setLayer}
          options={[
            { value: "suitability", label: "Suitability" },
            { value: "restoration", label: "Restoration" },
          ]}
        />
        {data?.run ? (
          layer === "suitability" ? (
            <>
              <CheckRow id="dash-conf-overlay" checked={confidenceOverlay} onChange={setConfidenceOverlay}>
                <span>Colour units by confidence instead of class</span>
              </CheckRow>
              <FilterPanel value={flt} onChange={setFlt} counts={counts} idPrefix="dash" shown={shown} total={polygons?.features.length ?? 0} />
            </>
          ) : (
            <fieldset className="m-0 grid min-w-0 gap-1 border-0 p-0">
              <legend className="h-panel mb-1">Restoration feasibility</legend>
              {FEAS.map((k) => (
                <CheckRow
                  key={k}
                  id={`dash-feas-${k}`}
                  checked={feas.has(k)}
                  onChange={(on) => {
                    const next = new Set(feas);
                    if (on) next.add(k);
                    else next.delete(k);
                    setFeas(next);
                  }}
                >
                  <span aria-hidden="true" className="size-4 shrink-0 rounded-xs" style={{ background: FEASIBILITY_META[k].color }} />
                  <span className="flex-1">{FEASIBILITY_META[k].label}</span>
                  <span className="text-xs text-ink-3 tnum">{feasCounts[k].n}</span>
                </CheckRow>
              ))}
              <Model2Caveats className="mt-2" />
              <p className="mt-1 text-xs text-ink-3">Model 2 applies to class 3 and 4 land only. Other units are shown muted. Outcomes shown elsewhere are simulated scenarios.</p>
            </fieldset>
          )
        ) : null}

        <section aria-labelledby="dash-status" className="grid gap-1.5 border-t border-line pt-4">
          <h3 id="dash-status" className="h-panel">
            Analysis status
          </h3>
          {bundle.status === "loading" ? (
            <Skeleton className="h-16" />
          ) : data?.run ? (
            <dl className="m-0 grid gap-1 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Suitability (Model 1)</dt>
                <dd className="m-0 text-ok">{data.run.demo ? "Demo dataset loaded" : "Complete"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Restoration (Model 2)</dt>
                <dd className="m-0 text-ok">{data.restoration ? `${fmtInt(data.restoration.features.length)} units` : "Not available"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Generated</dt>
                <dd className="m-0 text-ink-2">{fmtDateTime(data.run.created_at)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-3">Model version</dt>
                <dd className="m-0 font-mono text-xs text-ink-2">{String(data.run.metadata.model_version)}</dd>
              </div>
            </dl>
          ) : (
            <p className="m-0 text-sm text-ink-2">No analysis exists for this governorate in this release.</p>
          )}
        </section>
      </aside>

      {/* ---------------- statistics + selected unit ---------------- */}
      <aside aria-label="Statistics and selected land unit" className="grid grid-cols-[minmax(0,1fr)] content-start gap-5 border-t border-line p-4 lg:overflow-y-auto lg:border-s lg:border-t-0 lg:[grid-area:side]">
        {bundle.status === "loading" ? (
          <div className="grid gap-3" role="status" aria-label="Loading statistics">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-40" />
            <Skeleton className="h-24" />
          </div>
        ) : null}
        {bundle.status === "error" ? <ErrorState title="Could not load this region" message={bundle.error.message} onRetry={bundle.reload} /> : null}
        {bundle.status === "success" && !data?.run ? (
          <EmptyState
            title={`No analysis for ${regionInfo?.name?.replace("'", "’") ?? "this governorate"}`}
            action={
              <Button variant="primary" size="sm" onClick={() => changeRegion(DEFAULT_REGION)}>
                Switch to Ma&rsquo;an
              </Button>
            }
          >
            The boundary is shown for context, but no suitability or restoration analysis has been produced here yet. Pipelines are parameterised by region, so further governorates are added by configuration.
          </EmptyState>
        ) : null}

        {data?.run ? (
          <>
            <section aria-labelledby="dash-stats">
              <h2 id="dash-stats" className="h-panel mb-2">
                {layer === "suitability" ? "Land area by suitability class" : "Restoration potential (class 3 and 4 units)"}
              </h2>
              {layer === "suitability" ? (
                <>
                  <AreaStats run={data.run} activeClasses={flt.classes} />
                  <div className="mt-3">
                    <RunMetaNote run={data.run} />
                  </div>
                </>
              ) : (
                <div>
                  <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Restoration feasibility (scrollable table)">
                    <table className="data-table">
                      <caption className="visually-hidden">Model 2 feasibility by class, in hectares and dunums</caption>
                      <thead>
                        <tr>
                          <th scope="col">Feasibility</th>
                          <th scope="col" className="num">Units</th>
                          <th scope="col" className="num">Hectares</th>
                          <th scope="col" className="num">Dunums</th>
                        </tr>
                      </thead>
                      <tbody>
                        {FEAS.map((k) => (
                          <tr key={k} className={feas.has(k) ? undefined : "opacity-45"}>
                            <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-sm !normal-case !tracking-normal !text-ink">
                              <span className="flex items-center gap-2">
                                <span aria-hidden="true" className="size-4 rounded-xs" style={{ background: FEASIBILITY_META[k].color }} />
                                {FEASIBILITY_META[k].label}
                              </span>
                            </th>
                            <td className="num">{fmtInt(feasCounts[k].n)}</td>
                            <td className="num">{fmtHa(feasCounts[k].ha)}</td>
                            <td className="num">{fmtDunum(feasCounts[k].dunum)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-xs text-ink-3">
                    {DUNUM_DEFINITION}. Feasibility classes are Model 2 outputs with uncertainty intervals; the outcomes of any restoration scenario are simulated.
                  </p>
                </div>
              )}
            </section>

            <section aria-labelledby="dash-selected" className="border-t border-line pt-4">
              <h2 id="dash-selected" className="h-panel mb-3">
                Selected land unit
              </h2>
              {selected ? (
                <div className="grid gap-3">
                  {layer === "restoration" && selectedRest ? (
                    <p className="m-0 rounded-sm border border-line px-3 py-2 text-sm text-ink-2">
                      Model 2 feasibility: <strong className="text-ink">{FEASIBILITY_META[selectedRest.properties.feasibility.class].label}</strong> (score{" "}
                      {selectedRest.properties.feasibility.score}, interval {selectedRest.properties.feasibility.interval[0]}&ndash;{selectedRest.properties.feasibility.interval[1]}).
                    </p>
                  ) : null}
                  <PolygonDetail feature={selected} compact onClear={() => setSelectedId(null)} />
                </div>
              ) : (
                <EmptyState title="Select a land unit">
                  Click a polygon on the map to inspect its class, area, confidence and the factors behind it. Keyboard users can pick units from the list on the Suitability page.
                </EmptyState>
              )}
            </section>

            <section className="grid gap-2 border-t border-line pt-4" aria-label="Open analysis workspaces">
              <LinkButton href={`/suitability?region=${regionId}`} variant="secondary">
                Open suitability workspace <IconArrowRight className="size-4" />
              </LinkButton>
              <LinkButton href={`/restoration?region=${regionId}`} variant="secondary">
                Open restoration workspace <IconArrowRight className="size-4" />
              </LinkButton>
            </section>
          </>
        ) : null}

        <DemoNote />
        <p className="m-0 text-xs text-ink-3">
          Class meanings:{" "}
          {CLASS_LIST.map((c) => `${c.code} ${c.short.toLowerCase()}`).join(", ")}.{" "}
          <Link href="/#evidence" className="text-ink-2">
            How evidence is labelled
          </Link>
        </p>
      </aside>
    </main>
  );
}

export function DashboardView() {
  return (
    <Suspense fallback={<div className="p-6" role="status">Loading dashboard&hellip;</div>}>
      <DashboardInner />
    </Suspense>
  );
}
