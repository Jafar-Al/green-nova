"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { MapView } from "@/components/map";
import { MapLegend } from "@/components/map/MapLegend";
import { BasemapNote } from "@/components/data/BasemapNote";
import { ExportPanel } from "@/components/data/ExportPanel";
import { JobStatusPanel } from "@/components/data/JobStatusPanel";
import { PolygonDetail } from "@/components/data/PolygonDetail";
import { PolygonList } from "@/components/data/PolygonList";
import { Model2Caveats } from "@/components/data/Model2Caveats";
import { RegionSelectors } from "@/components/data/RegionSelectors";
import {
  ConstraintsForm,
  FeasibilityChip,
  InterventionList,
  LimitingFactorList,
  OutcomeComparison,
  ScenarioCompare,
  tiersFrom,
} from "@/components/data/RestorationParts";
import { Button, ClassChip, Disclosure, Segmented, Skeleton } from "@/components/ui/primitives";
import { DemoNote, EmptyState, ErrorState, OfflineBanner } from "@/components/ui/states";
import { IconArrowRight } from "@/components/ui/icons";
import { CLASS5_NOTE, RESTORABLE_CLASS_CODES, SUITABILITY_CLASSES } from "@/lib/classes";
import type { SuitabilityClassCode } from "@/lib/contract";
import { IS_DEMO_MODE } from "@/lib/config";
import { fmtDunum, fmtHa, fmtInt, fmtNum } from "@/lib/format";
import { geometryBBox } from "@/lib/geo";
import { useProvider } from "@/lib/hooks";
import { currentUnits, selectionUnits, simulatedUnits } from "@/lib/layers";
import { DEFAULT_REGION, useJob, useRegionBundle, useRegionList, useRegionParam } from "@/lib/region-data";
import { DEFAULT_CONSTRAINTS, availableWaterSources, chooseScenario, evaluateRun, summariseOutcome } from "@/lib/restoration";
import type { RestorationConstraints, RestorationRun } from "@/lib/types";
import { DUNUM_DEFINITION } from "@/lib/units";

type MapMode = "current" | "simulated";
const RESTORABLE = new Set<SuitabilityClassCode>(RESTORABLE_CLASS_CODES);

function RestorationInner() {
  const provider = useProvider();
  const [regionId, setRegionId] = useRegionParam();
  const list = useRegionList(provider);
  const bundle = useRegionBundle(provider, regionId);
  const { job, error, starting, start, cancel, reset } = useJob(provider);
  const [simulateFailure, setSimulateFailure] = useState(false);

  const [selection, setSelection] = useState<string[]>([]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [constraints, setConstraints] = useState<RestorationConstraints>(DEFAULT_CONSTRAINTS);
  const [touched, setTouched] = useState(false);
  const [preference, setPreference] = useState("best");
  const [mapMode, setMapMode] = useState<MapMode>("simulated");
  const [runState, setRunState] = useState<{ jobId: string; run: RestorationRun | null; error: string | null } | null>(null);
  const [shownRows, setShownRows] = useState(25);

  const data = bundle.status === "success" ? bundle.data : null;
  const polygons = data?.polygons ?? null;
  const regionInfo = list.data?.regions.find((r) => r.id === regionId);
  const regionName = regionInfo?.name.replace("'", "’") ?? regionId;

  const sources = useMemo(() => availableWaterSources(data?.restoration?.features ?? []), [data?.restoration]);
  // until the user edits the form, every water source named by the data is available
  const effectiveConstraints = useMemo<RestorationConstraints>(
    () => (touched ? constraints : { ...constraints, allowed_water_sources: sources }),
    [touched, constraints, sources],
  );
  const setC = (c: RestorationConstraints) => {
    setTouched(true);
    setConstraints(c);
  };

  // fetch results once the job completes; state is keyed by job id so stale results never show
  useEffect(() => {
    if (job?.state !== "succeeded" || job.kind !== "restoration") return;
    let alive = true;
    const jobId = job.id;
    provider.getRestorationRun(jobId).then(
      (r) => alive && setRunState({ jobId, run: r, error: null }),
      (e: unknown) => alive && setRunState({ jobId, run: null, error: e instanceof Error ? e.message : "Results could not be loaded." }),
    );
    return () => {
      alive = false;
    };
  }, [job, provider]);
  const runMatches = !!(runState && job && runState.jobId === job.id && job.state === "succeeded");
  const run = runMatches ? runState!.run : null;
  const runError = runMatches ? runState!.error : null;

  const m1ById = useMemo(() => new Map((polygons?.features ?? []).map((f) => [f.properties.id, f] as const)), [polygons]);
  const classCount = useMemo(() => {
    const c: Record<number, number> = {};
    for (const f of polygons?.features ?? []) c[f.properties.class_code] = (c[f.properties.class_code] ?? 0) + 1;
    return c;
  }, [polygons]);
  const restorableFeatures = useMemo(() => (polygons?.features ?? []).filter((f) => RESTORABLE.has(f.properties.class_code)), [polygons]);

  const evals = useMemo(() => (run ? evaluateRun(run.features, effectiveConstraints) : []), [run, effectiveConstraints]);
  const outcome = useMemo(() => summariseOutcome(evals, preference), [evals, preference]);
  const tiers = useMemo(() => tiersFrom(data?.restoration?.features ?? []), [data?.restoration]);

  const analysedIds = useMemo(() => new Set(run?.features.map((f) => f.properties.source_polygon_id) ?? []), [run]);
  const postClass = useMemo(() => {
    const m = new Map<string, SuitabilityClassCode>();
    for (const ev of evals) {
      const ch = chooseScenario(ev, preference);
      if (ch && ch.post_class_code < ev.feature.properties.current_class_code) m.set(ev.feature.properties.source_polygon_id, ch.post_class_code);
    }
    return m;
  }, [evals, preference]);

  const units = useMemo(() => {
    if (!polygons) return null;
    if (run) return mapMode === "simulated" ? simulatedUnits(polygons, analysedIds, postClass) : currentUnits(polygons, analysedIds);
    return selectionUnits(polygons, RESTORABLE);
  }, [polygons, run, mapMode, analysedIds, postClass]);

  const selTotals = useMemo(() => {
    let ha = 0;
    let dunum = 0;
    for (const id of selection) {
      const p = m1ById.get(id)?.properties;
      if (p) {
        ha += p.area_ha;
        dunum += p.area_dunum;
      }
    }
    return { ha, dunum };
  }, [selection, m1ById]);

  const changeRegion = (id: string) => {
    reset();
    setSelection([]);
    setFocusId(null);
    setTouched(false);
    setRegionId(id);
  };

  const rejectReason = (id: string): string | null => {
    const f = m1ById.get(id);
    if (!f) return null;
    const c = f.properties.class_code;
    if (c === 5) return CLASS5_NOTE;
    if (!RESTORABLE.has(c)) return `Class ${c} (${SUITABILITY_CLASSES[c].label}): restoration analysis applies to class 3 and 4 land.`;
    return null;
  };

  const toggle = (id: string) => {
    const why = rejectReason(id);
    setFocusId(id);
    if (why) {
      setNotice(`${id}: ${why}`);
      return;
    }
    setNotice("");
    if (run) return; // selection is locked to the completed run; use "Edit selection"
    setSelection((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  };

  const addClass = (c: SuitabilityClassCode) => {
    const ids = (polygons?.features ?? []).filter((f) => f.properties.class_code === c).map((f) => f.properties.id);
    setSelection((cur) => [...new Set([...cur, ...ids])]);
    setNotice("");
  };

  const blocked =
    bundle.status !== "success"
      ? "Loading the region…"
      : !data?.run
        ? `No analysis exists for ${regionName} in this release.`
        : selection.length === 0
          ? "Select at least one class 3 or 4 land unit first."
          : null;

  const focusM1 = focusId ? (m1ById.get(focusId) ?? null) : null;
  const focusEval = evals.find((e) => e.feature.properties.source_polygon_id === focusId) ?? null;

  return (
    <main
      id="main"
      tabIndex={-1}
      className="grid min-h-[calc(100dvh-var(--demo-h)-var(--app-h))] grid-cols-1 outline-none lg:h-[calc(100dvh-var(--demo-h)-var(--app-h))] lg:min-h-0 lg:grid-cols-[21rem_minmax(0,1fr)_27rem] lg:[grid-template-areas:'work_map_side']"
    >
      <h1 className="visually-hidden">Restoration potential analysis (Model 2)</h1>

      <section aria-label="Satellite map for selecting and comparing land units" className="relative h-[62dvh] min-h-[24rem] lg:h-auto lg:min-h-0 lg:[grid-area:map]">
        <MapView
          className="size-full"
          ariaLabel={`Satellite map of ${regionName}. ${run ? "Showing analysed land units." : "Click class 3 and 4 land units to select them for restoration analysis."}`}
          boundary={data?.boundary ?? null}
          units={units}
          selectedIds={run ? (focusId ? [focusId] : []) : selection}
          fitTo={data ? geometryBBox(data.boundary.geometry) : null}
          focusId={focusId}
          onSelect={toggle}
          getTooltip={(id) => {
            const p = m1ById.get(id)?.properties;
            return p ? `${p.id} · class ${p.class_code} · ${fmtHa(p.area_ha)} ha` : null;
          }}
          overlay={<MapLegend mode={run && mapMode === "simulated" ? "simulated" : "class"} />}
        />
        {run ? (
          <div className="absolute inset-x-2 bottom-12 z-10 mx-auto w-[min(26rem,calc(100%-1rem))] md:bottom-10">
            <div className="rounded-sm border border-line-strong bg-canvas/95 p-1.5 shadow-[0_6px_16px_rgb(0_0_0/0.4)]">
              <Segmented<MapMode>
                legend="Map view"
                name="rest-mapmode"
                value={mapMode}
                onChange={setMapMode}
                options={[
                  { value: "current", label: "Current (Model 1)" },
                  { value: "simulated", label: "Simulated after restoration" },
                ]}
              />
            </div>
          </div>
        ) : null}
      </section>

      {/* ---------------- workflow ---------------- */}
      <aside aria-label="Restoration workflow" className="grid grid-cols-[minmax(0,1fr)] content-start gap-5 border-t border-line p-4 lg:overflow-y-auto lg:border-e lg:border-t-0 lg:[grid-area:work]">
        <div>
          <h2 className="h-page !text-[1.5rem]">Restoration potential</h2>
          <p className="mt-1 text-sm text-ink-2">
            Model 2 asks of currently unsuitable land: what prevents cultivation, can it be reversed, what would it take, and what could be achieved. Outcomes are simulated scenarios, never observed results.
          </p>
        </div>
        <OfflineBanner />
        <Model2Caveats />
        <RegionSelectors list={list.data} regionId={regionId} onRegion={changeRegion} idPrefix="rest" loading={list.status === "loading"} />

        <section aria-labelledby="r-step1" className="grid gap-2 border-t border-line pt-4">
          <h3 id="r-step1" className="h-panel">
            1. Select unsuitable land
          </h3>
          {data?.run ? (
            <>
              <p className="m-0 text-sm text-ink-2" aria-live="polite">
                <strong className="text-ink tnum">{fmtInt(selection.length)}</strong> units selected &middot; <span className="tnum">{fmtHa(selTotals.ha)}</span> ha &middot;{" "}
                <span className="tnum">{fmtDunum(selTotals.dunum)}</span> dunum
              </p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => addClass(3)} disabled={!!run}>
                  Add all class 3 ({classCount[3] ?? 0})
                </Button>
                <Button size="sm" onClick={() => addClass(4)} disabled={!!run}>
                  Add all class 4 ({classCount[4] ?? 0})
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setSelection([])} disabled={!!run || selection.length === 0}>
                  Clear
                </Button>
              </div>
              <p className="m-0 text-xs text-ink-3">
                Click polygons on the map or tick units in the list. {classCount[5] ?? 0} class 5 units are shown hatched and cannot be selected: {CLASS5_NOTE}
              </p>
              <p role="status" className="m-0 text-xs text-warn">
                {notice}
              </p>
            </>
          ) : (
            <p className="m-0 text-sm text-ink-2">Choose a region with a suitability analysis first.</p>
          )}
        </section>

        <section aria-labelledby="r-step2" className="grid gap-2 border-t border-line pt-4">
          <h3 id="r-step2" className="h-panel">
            2. Set your constraints
          </h3>
          <ConstraintsForm value={effectiveConstraints} onChange={setC} waterSources={sources} tiers={tiers} preference={preference} onPreference={setPreference} idPrefix="rest-c" />
          <p className="m-0 text-xs text-ink-3">Constraints filter and rank the scenarios Model 2 produced. Changing them after a run updates the results instantly and does not re-run the model.</p>
        </section>

        <div className="border-t border-line pt-4">
          <JobStatusPanel
            idPrefix="rest-job"
            title="3. Run restoration analysis"
            startLabel="Run restoration analysis"
            idleText={<>Analyses the selected units for limiting factors, feasibility, interventions and simulated scenarios. {IS_DEMO_MODE ? "This preview replays precomputed synthetic results." : "Model 2 runs on the selected units; scenario outcomes are simulated, never observed."}</>}
            job={job}
            error={error}
            starting={starting}
            onStart={() => void start(() => provider.startRestorationJob({ region_id: regionId, polygon_ids: selection }, { simulateFailure }))}
            onCancel={() => void cancel()}
            startBlockedReason={blocked}
            simulateFailure={simulateFailure}
            onSimulateFailure={setSimulateFailure}
            completeNote={run ? `${fmtInt(run.features.length)} units analysed${run.rejected.length ? `, ${run.rejected.length} not analysable` : ""}.` : undefined}
          />
          {run ? (
            <div className="mt-3">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => reset()}
              >
                Edit selection
              </Button>
            </div>
          ) : null}
        </div>

        <BasemapNote />
        <DemoNote />
      </aside>

      {/* ---------------- results ---------------- */}
      <aside aria-label="Selected units, results and export" className="grid grid-cols-[minmax(0,1fr)] content-start gap-5 border-t border-line p-4 lg:overflow-y-auto lg:border-s lg:border-t-0 lg:[grid-area:side]">
        {bundle.status === "loading" ? (
          <div className="grid gap-3" role="status" aria-label="Loading region">
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-40" />
          </div>
        ) : null}
        {bundle.status === "error" ? <ErrorState title="Could not load this region" message={bundle.error.message} onRetry={bundle.reload} /> : null}
        {bundle.status === "success" && !data?.run ? (
          <EmptyState
            title={`No analysis for ${regionName}`}
            action={
              <Button size="sm" variant="primary" onClick={() => changeRegion(DEFAULT_REGION)}>
                Switch to Ma&rsquo;an
              </Button>
            }
          >
            Restoration potential builds on a suitability analysis. None exists for this governorate in this release.
          </EmptyState>
        ) : null}
        {runError ? <ErrorState title="Results could not be loaded" message={runError} /> : null}

        {data?.run && !run ? (
          <>
            <PolygonList
              label="Unsuitable land (class 3 and 4)"
              features={restorableFeatures}
              selectedIds={selection}
              focusId={focusId}
              multi
              onToggle={toggle}
              onFocus={setFocusId}
              maxHeightClass="max-h-96"
            />
            {focusM1 ? (
              <section aria-labelledby="r-focus-m1" className="border-t border-line pt-4">
                <h2 id="r-focus-m1" className="h-panel mb-3">
                  Land unit (Model 1)
                </h2>
                <PolygonDetail feature={focusM1} compact onClear={() => setFocusId(null)} />
              </section>
            ) : null}
          </>
        ) : null}

        {run ? (
          <>
            <section aria-labelledby="r-summary">
              <h2 id="r-summary" className="h-panel mb-2">
                Results for {fmtInt(run.features.length)} analysed units
              </h2>
              <dl className="m-0 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <div>
                  <dt className="text-xs text-ink-3">With a viable scenario</dt>
                  <dd className="m-0 font-semibold tnum">{outcome.counts.with_scenario}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-3">Excluded by your constraints</dt>
                  <dd className="m-0 font-semibold tnum">{outcome.counts.excluded}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-3">No viable scenario</dt>
                  <dd className="m-0 font-semibold tnum">{outcome.counts.no_viable_scenario}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-3">Simulated improvement</dt>
                  <dd className="m-0 font-semibold tnum">
                    {fmtHa(outcome.improved_ha)} ha <span className="font-normal text-ink-3">({fmtDunum(outcome.improved_ha * 10)} dunum)</span>
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-xs text-ink-3">Water need of the chosen scenarios (simulated range)</dt>
                  <dd className="m-0 font-semibold tnum">
                    {fmtNum(outcome.water_mm3_yr.low, 2)}&ndash;{fmtNum(outcome.water_mm3_yr.high, 2)} <span className="font-normal text-ink-3">million m&sup3;/yr</span>
                  </dd>
                </div>
              </dl>
              {run.rejected.length > 0 ? (
                <Disclosure summary={`${run.rejected.length} requested units were not analysed`} className="mt-2 rounded-sm border border-line px-3">
                  <ul className="m-0 list-disc ps-4 text-xs text-ink-2">
                    {run.rejected.slice(0, 8).map((r) => (
                      <li key={r.id}>
                        <span className="font-mono">{r.id}</span>: {r.reason}
                      </li>
                    ))}
                  </ul>
                </Disclosure>
              ) : null}
            </section>

            <section aria-labelledby="r-compare" className="border-t border-line pt-4">
              <h2 id="r-compare" className="h-panel mb-2">
                Current vs simulated post-restoration suitability
              </h2>
              <OutcomeComparison out={outcome} />
              <p className="mt-2 text-xs text-ink-3">
                {DUNUM_DEFINITION}. The simulated column applies the scenario chosen in step 2 to every unit that has a viable one; other units keep their current class.
              </p>
            </section>

            <section aria-labelledby="r-units" className="border-t border-line pt-4">
              <h2 id="r-units" className="h-panel mb-2">
                Units
              </h2>
              <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Analysed units (scrollable table)">
                <table className="data-table min-w-[30rem]">
                  <caption className="visually-hidden">Analysed units with feasibility and the scenario chosen under your constraints</caption>
                  <thead>
                    <tr>
                      <th scope="col">Unit</th>
                      <th scope="col">Feasibility</th>
                      <th scope="col">Chosen scenario (simulated)</th>
                      <th scope="col" className="num">Water m&sup3;/ha/yr</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evals.slice(0, shownRows).map((ev) => {
                      const p = ev.feature.properties;
                      const ch = chooseScenario(ev, preference);
                      const isFocus = focusId === p.source_polygon_id;
                      return (
                        <tr key={p.id} className={isFocus ? "bg-[color-mix(in_oklab,var(--accent)_12%,transparent)]" : undefined}>
                          <td className="min-w-[9.5rem] whitespace-nowrap">
                            <button type="button" onClick={() => setFocusId(p.source_polygon_id)} aria-pressed={isFocus} className="text-start font-mono text-xs underline decoration-line-strong underline-offset-4 hover:text-accent">
                              {p.source_polygon_id}
                            </button>
                            <span className="block text-xs text-ink-3">class {p.current_class_code} &middot; {fmtHa(p.area_ha)} ha</span>
                          </td>
                          <td>
                            <FeasibilityChip cls={p.feasibility.class} />
                            <span className="block text-xs text-ink-3 tnum">
                              {p.feasibility.score} ({p.feasibility.interval[0]}&ndash;{p.feasibility.interval[1]})
                            </span>
                          </td>
                          <td className="text-xs text-ink-2">
                            {ch ? (
                              <>
                                {ch.name.split(":")[0]}
                                <span className="block text-ink-3">to class {ch.post_class_code}, simulated</span>
                              </>
                            ) : ev.excludedReasons.length ? (
                              <span className="text-ink-3">Excluded: {ev.excludedReasons[0]}</span>
                            ) : (
                              <span className="text-ink-3">No viable scenario</span>
                            )}
                          </td>
                          <td className="num text-xs">{ch ? fmtNum(ch.water_requirement_m3_ha_yr.central, 0) : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {shownRows < evals.length ? (
                <div className="mt-2">
                  <Button size="sm" variant="ghost" onClick={() => setShownRows((n) => n + 25)}>
                    Show more ({evals.length - shownRows} left)
                  </Button>
                </div>
              ) : null}
            </section>

            <section aria-labelledby="r-focus" className="border-t border-line pt-4">
              <h2 id="r-focus" className="h-panel mb-3">
                Unit detail: constraints, interventions, scenarios
              </h2>
              {focusEval ? (
                <div className="grid gap-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="m-0 font-mono text-xs text-ink-3">{focusEval.feature.properties.source_polygon_id}</p>
                    <Link href={`/land/${encodeURIComponent(focusEval.feature.properties.source_polygon_id)}`} className="inline-flex items-center gap-1 text-sm font-semibold text-accent">
                      Full land details <IconArrowRight className="size-4" />
                    </Link>
                  </div>
                  <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
                    <ClassChip code={focusEval.feature.properties.current_class_code as SuitabilityClassCode} short /> <span aria-hidden="true">&rarr;</span> <FeasibilityChip cls={focusEval.feature.properties.feasibility.class} />
                  </p>
                  <p className="m-0 text-xs text-ink-3">
                    Feasibility score {focusEval.feature.properties.feasibility.score}, interval {focusEval.feature.properties.feasibility.interval[0]}&ndash;{focusEval.feature.properties.feasibility.interval[1]}, confidence{" "}
                    {focusEval.feature.properties.feasibility.confidence}. Uncertainty is part of the result; the interval is not a guarantee.
                  </p>
                  {focusEval.excludedReasons.length > 0 ? (
                    <p role="status" className="m-0 rounded-sm border border-warn/60 px-3 py-2 text-xs text-ink-2">
                      Excluded by your constraints: {focusEval.excludedReasons.join(" ")}
                    </p>
                  ) : null}
                  <div>
                    <h3 className="h-panel mb-1">What prevents cultivation</h3>
                    <LimitingFactorList factors={focusEval.feature.properties.limiting_factors} />
                  </div>
                  <div>
                    <h3 className="h-panel mb-1">Recommended interventions</h3>
                    <InterventionList interventions={focusEval.feature.properties.interventions} />
                  </div>
                  <div>
                    <h3 className="h-panel mb-1">Scenario comparison</h3>
                    <ScenarioCompare ev={focusEval} interventions={focusEval.feature.properties.interventions} />
                  </div>
                  <p className="m-0 text-xs text-ink-3">
                    Provenance: {focusEval.feature.properties.provenance.model_version}. Source studies:{" "}
                    {focusEval.feature.properties.provenance.source_studies.length ? focusEval.feature.properties.provenance.source_studies.join("; ") : IS_DEMO_MODE ? "none attached to demonstration data" : "none attached to this result"}.
                  </p>
                </div>
              ) : (
                <EmptyState title="Choose a unit">Pick a unit from the table or the map to see why it is limited, which interventions apply and how the scenarios compare.</EmptyState>
              )}
            </section>

            <div className="border-t border-line pt-4">
              <ExportPanel
                idPrefix="rest-export"
                title="Export report"
                capabilities={provider.capabilities()}
                run={(format) => provider.exportRestoration(run.job_id, format, { constraints: effectiveConstraints, preference })}
                items={[
                  { format: "report_html", label: "Detailed report (HTML)", description: "Printable report: constraints, current vs simulated, per-unit results, evidence key. Use Print > Save as PDF." },
                  { format: "csv", label: "Results table (CSV)", description: "One row per unit with feasibility, chosen scenario and water ranges." },
                  { format: "geojson", label: "Results (GeoJSON)", description: "Polygons with full Model 2 properties and your constraint outcome." },
                  { format: "pdf", label: "Report (PDF)", description: "Server-rendered PDF." },
                ]}
              />
            </div>
          </>
        ) : null}
      </aside>
    </main>
  );
}

export function RestorationView() {
  return (
    <Suspense fallback={<div className="p-6" role="status">Loading restoration workspace&hellip;</div>}>
      <RestorationInner />
    </Suspense>
  );
}
