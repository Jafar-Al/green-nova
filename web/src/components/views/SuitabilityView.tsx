"use client";

import { Suspense, useMemo, useState } from "react";
import { MapView } from "@/components/map";
import { MapLegend } from "@/components/map/MapLegend";
import { AreaStats } from "@/components/data/AreaStats";
import { BasemapNote } from "@/components/data/BasemapNote";
import { ExportPanel } from "@/components/data/ExportPanel";
import { FilterPanel } from "@/components/data/FilterPanel";
import { JobStatusPanel } from "@/components/data/JobStatusPanel";
import { PolygonDetail } from "@/components/data/PolygonDetail";
import { PolygonList } from "@/components/data/PolygonList";
import { RegionSelectors } from "@/components/data/RegionSelectors";
import { RunMetaNote } from "@/components/data/RunMetaNote";
import { Button, Segmented, Skeleton } from "@/components/ui/primitives";
import { DemoNote, EmptyState, ErrorState, OfflineBanner } from "@/components/ui/states";
import type { SuitabilityClassCode } from "@/lib/contract";
import { IS_DEMO_MODE } from "@/lib/config";
import { fmtHa, fmtInt } from "@/lib/format";
import { geometryBBox } from "@/lib/geo";
import { useProvider } from "@/lib/hooks";
import { defaultSuitabilityFilters, passesSuitabilityFilters, suitabilityUnits, type SuitabilityFilters } from "@/lib/layers";
import { DEFAULT_REGION, useJob, useRegionBundle, useRegionList, useRegionParam } from "@/lib/region-data";

type Overlay = "class" | "confidence";

function SuitabilityInner() {
  const provider = useProvider();
  const [regionId, setRegionId] = useRegionParam();
  const list = useRegionList(provider);
  const bundle = useRegionBundle(provider, regionId);
  const { job, error, starting, start, cancel, reset } = useJob(provider);
  const [simulateFailure, setSimulateFailure] = useState(false);
  const [viewLatest, setViewLatest] = useState(false);
  const [flt, setFlt] = useState<SuitabilityFilters>(defaultSuitabilityFilters);
  const [overlay, setOverlay] = useState<Overlay>("class");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const data = bundle.status === "success" ? bundle.data : null;
  const polygons = data?.polygons ?? null;
  const regionInfo = list.data?.regions.find((r) => r.id === regionId);
  const regionName = regionInfo?.name.replace("'", "’") ?? regionId;
  const hasResults = !!data?.run && (job?.state === "succeeded" || viewLatest);

  const filtered = useMemo(() => (polygons?.features ?? []).filter((f) => passesSuitabilityFilters(f, flt)), [polygons, flt]);
  const units = useMemo(() => (hasResults && polygons ? suitabilityUnits(polygons, flt, overlay) : null), [hasResults, polygons, flt, overlay]);
  const counts = useMemo(() => {
    const c: Partial<Record<SuitabilityClassCode, number>> = {};
    for (const f of polygons?.features ?? []) c[f.properties.class_code] = (c[f.properties.class_code] ?? 0) + 1;
    return c;
  }, [polygons]);
  const selected = polygons?.features.find((f) => f.properties.id === selectedId) ?? null;

  const changeRegion = (id: string) => {
    setSelectedId(null);
    setViewLatest(false);
    reset();
    setRegionId(id);
  };

  const blocked =
    bundle.status === "loading"
      ? "Loading the region…"
      : bundle.status === "error"
        ? "The region could not be loaded."
        : data && !data.run
          ? `No analysis can be run for ${regionName} in this release. The demonstration covers Ma’an only.`
          : null;

  return (
    <main
      id="main"
      tabIndex={-1}
      className="grid min-h-[calc(100dvh-var(--demo-h)-var(--app-h))] grid-cols-1 outline-none lg:h-[calc(100dvh-var(--demo-h)-var(--app-h))] lg:min-h-0 lg:grid-cols-[21rem_minmax(0,1fr)_24rem] lg:[grid-template-areas:'work_map_side']"
    >
      <h1 className="visually-hidden">Land suitability analysis (Model 1)</h1>

      <section aria-label="Satellite map with suitability overlay" className="relative h-[62dvh] min-h-[24rem] lg:h-auto lg:min-h-0 lg:[grid-area:map]">
        <MapView
          className="size-full"
          ariaLabel={`Satellite map of ${regionName}${hasResults ? " with land suitability polygons" : ""}`}
          boundary={data?.boundary ?? null}
          units={units}
          selectedIds={selectedId ? [selectedId] : []}
          fitTo={data ? geometryBBox(data.boundary.geometry) : null}
          focusId={selectedId}
          onSelect={(id) => setSelectedId((cur) => (cur === id ? null : id))}
          onBackgroundClick={() => setSelectedId(null)}
          getTooltip={(id) => {
            const p = polygons?.features.find((x) => x.properties.id === id)?.properties;
            return p ? `${p.id} · class ${p.class_code} · ${fmtHa(p.area_ha)} ha · conf ${p.confidence.toFixed(2)}` : null;
          }}
          overlay={hasResults ? <MapLegend mode={overlay} counts={overlay === "class" ? counts : undefined} /> : null}
        />
      </section>

      {/* ------------- workflow ------------- */}
      <aside aria-label="Analysis workflow" className="grid grid-cols-[minmax(0,1fr)] content-start gap-5 border-t border-line p-4 lg:overflow-y-auto lg:border-e lg:border-t-0 lg:[grid-area:work]">
        <div>
          <h2 className="h-page !text-[1.5rem]">Land suitability</h2>
          <p className="mt-1 text-sm text-ink-2">Model 1 classifies every land unit of a governorate into five classes, with area, confidence and the factors behind each class.</p>
        </div>
        <OfflineBanner />

        <section aria-labelledby="s-step1" className="grid gap-3">
          <h3 id="s-step1" className="h-panel">
            1. Select a region
          </h3>
          <RegionSelectors list={list.data} regionId={regionId} onRegion={changeRegion} idPrefix="suit" loading={list.status === "loading"} />
        </section>

        <div className="border-t border-line pt-4">
          <JobStatusPanel
            idPrefix="suit-job"
            title="2. Run the analysis"
            startLabel="Start suitability analysis"
            idleText={
              <>
                Starts a suitability analysis for <strong className="text-ink">{regionName}</strong>. {IS_DEMO_MODE ? "In this preview the run replays a precomputed synthetic result so you can explore every state of the workflow." : "The region-wide result precomputed by Model 1 is loaded, validated against the data contract and shown on the map."}
              </>
            }
            job={job}
            error={error}
            starting={starting}
            onStart={() => void start(() => provider.startSuitabilityJob(regionId, { simulateFailure }))}
            onCancel={() => void cancel()}
            startBlockedReason={blocked}
            simulateFailure={simulateFailure}
            onSimulateFailure={setSimulateFailure}
            completeNote={data?.run ? `${fmtInt(data.run.polygon_count)} land units classified.` : undefined}
          />
          {data?.run && !hasResults && !job ? (
            <p className="mt-3 text-xs text-ink-3">
              Already have results?{" "}
              <button type="button" className="text-ink underline" onClick={() => setViewLatest(true)}>
                Open the latest precomputed run
              </button>
              .
            </p>
          ) : null}
        </div>

        {hasResults && polygons && data?.run ? (
          <section aria-labelledby="s-step3" className="grid gap-4 border-t border-line pt-4">
            <h3 id="s-step3" className="h-panel">
              3. Explore the results
            </h3>
            <Segmented<Overlay>
              legend="Overlay"
              name="suit-overlay"
              value={overlay}
              onChange={setOverlay}
              options={[
                { value: "class", label: "Class" },
                { value: "confidence", label: "Confidence" },
              ]}
            />
            <FilterPanel value={flt} onChange={setFlt} counts={counts} idPrefix="suit" shown={filtered.length} total={polygons.features.length} />
          </section>
        ) : null}

        <BasemapNote />
        <DemoNote />
      </aside>

      {/* ------------- results ------------- */}
      <aside aria-label="Results, selected land unit and export" className="grid grid-cols-[minmax(0,1fr)] content-start gap-5 border-t border-line p-4 lg:overflow-y-auto lg:border-s lg:border-t-0 lg:[grid-area:side]">
        {bundle.status === "loading" ? (
          <div className="grid gap-3" role="status" aria-label="Loading region">
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-32" />
          </div>
        ) : null}
        {bundle.status === "error" ? <ErrorState title="Could not load this region" message={bundle.error.message} onRetry={bundle.reload} /> : null}

        {bundle.status === "success" && !data?.run ? (
          <EmptyState
            title={`No suitability analysis for ${regionName}`}
            action={
              <Button size="sm" variant="primary" onClick={() => changeRegion(DEFAULT_REGION)}>
                Switch to Ma&rsquo;an
              </Button>
            }
          >
            {IS_DEMO_MODE ? "Only the demonstration region has results in this release." : "Only Ma\u2019an has results in this release."} Governorates are added by configuration once their pipelines have run.
          </EmptyState>
        ) : null}

        {data?.run && !hasResults ? (
          <EmptyState title="No results yet">
            Run the analysis to see land units drawn on the map. You will then be able to click any polygon, review its area in hectares and dunums, its confidence and the factors that drove its class, filter by class, confidence or size, and export the results.
          </EmptyState>
        ) : null}

        {hasResults && data?.run && polygons ? (
          <>
            <section aria-labelledby="s-stats">
              <h2 id="s-stats" className="h-panel mb-2">
                Results for {regionName}
              </h2>
              <AreaStats run={data.run} activeClasses={flt.classes} />
              <div className="mt-3">
                <RunMetaNote run={data.run} />
              </div>
            </section>

            <section aria-labelledby="s-selected" className="border-t border-line pt-4">
              <h2 id="s-selected" className="h-panel mb-3">
                Selected land unit
              </h2>
              {selected ? (
                <PolygonDetail feature={selected} onClear={() => setSelectedId(null)} />
              ) : (
                <EmptyState title="Select a land unit">Click a polygon on the map or choose one from the list below. Its class, area, confidence and factors appear here.</EmptyState>
              )}
            </section>

            <div className="border-t border-line pt-4">
              <PolygonList
                label="Land units"
                features={filtered}
                selectedIds={selectedId ? [selectedId] : []}
                focusId={selectedId}
                onToggle={(id) => setSelectedId((cur) => (cur === id ? null : id))}
              />
            </div>

            <div className="border-t border-line pt-4">
              <ExportPanel
                idPrefix="suit-export"
                capabilities={provider.capabilities()}
                run={(format) => provider.exportSuitability(regionId, format)}
                items={[
                  { format: "geojson", label: "Land units (GeoJSON)", description: "All polygons with class, area, confidence and factors. EPSG:4326." },
                  { format: "csv", label: "Land units table (CSV)", description: "One row per unit: class, hectares, dunums, confidence, limiting factors." },
                  { format: "summary_json", label: "Class summary (JSON)", description: "Per-class unit count, area and share, plus run metadata." },
                  { format: "geotiff", label: "Suitability raster (GeoTIFF)", description: "Cloud-optimised GeoTIFF of the class raster." },
                ]}
              />
            </div>
          </>
        ) : null}
      </aside>
    </main>
  );
}

export function SuitabilityView() {
  return (
    <Suspense fallback={<div className="p-6" role="status">Loading suitability workspace&hellip;</div>}>
      <SuitabilityInner />
    </Suspense>
  );
}
