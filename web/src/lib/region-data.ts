"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { RestorationCollection, SuitabilityCollection } from "./contract";
import { useAsync } from "./hooks";
import { ProviderError, type AnalysisJob, type Country, type DataProvider, type RegionBoundary, type RegionInfo, type SuitabilityRun } from "./types";

export const DEFAULT_REGION = "jo-maan";

export interface RegionBundle {
  boundary: RegionBoundary;
  run: SuitabilityRun | null;
  polygons: SuitabilityCollection | null;
  restoration: RestorationCollection | null;
}

const cache = new Map<string, Promise<RegionBundle>>();

/** Loads everything the views need for a region once per page session; failures are not cached. */
export function loadRegionBundle(provider: DataProvider, regionId: string): Promise<RegionBundle> {
  const key = `${provider.id}:${regionId}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const p = (async (): Promise<RegionBundle> => {
    const boundary = await provider.getRegionBoundary(regionId);
    const run = await provider.getSuitabilityRun(regionId);
    if (!run) return { boundary, run: null, polygons: null, restoration: null };
    const [polygons, restoration] = await Promise.all([provider.getSuitabilityPolygons(regionId), provider.getRestorationLayer(regionId)]);
    return { boundary, run, polygons, restoration };
  })().catch((e) => {
    cache.delete(key);
    throw e;
  });
  cache.set(key, p);
  return p;
}

export function useRegionBundle(provider: DataProvider, regionId: string) {
  return useAsync(() => loadRegionBundle(provider, regionId), [provider, regionId]);
}

export interface RegionList {
  countries: Country[];
  regions: RegionInfo[];
}

export function useRegionList(provider: DataProvider) {
  return useAsync<RegionList>(async () => {
    const countries = await provider.listCountries();
    const regions = await provider.listRegions(countries[0]?.code ?? "JO");
    return { countries, regions };
  }, [provider]);
}

/** Region id kept in the URL (?region=jo-maan) so views are linkable; defaults to Ma'an. */
export function useRegionParam(): [string, (id: string) => void] {
  const router = useRouter();
  const params = useSearchParams();
  const region = params.get("region") || DEFAULT_REGION;
  const set = useCallback(
    (id: string) => {
      const next = new URLSearchParams(params.toString());
      next.set("region", id);
      router.replace(`?${next.toString()}`, { scroll: false });
    },
    [params, router],
  );
  return [region, set];
}

/** Drives a start -> poll -> done lifecycle for either kind of job. */
export function useJob(provider: DataProvider) {
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [error, setError] = useState<{ message: string; code?: string } | null>(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const poll = useCallback(
    (id: string) => {
      const tick = async () => {
        try {
          const j = await provider.getJob(id);
          if (!alive.current) return;
          setJob(j);
          if (j.state === "queued" || j.state === "running") timer.current = setTimeout(tick, 350);
        } catch (e) {
          if (!alive.current) return;
          setError({ message: e instanceof Error ? e.message : String(e), code: e instanceof ProviderError ? e.code : undefined });
        }
      };
      void tick();
    },
    [provider],
  );

  const start = useCallback(
    async (starter: () => Promise<AnalysisJob>) => {
      if (timer.current) clearTimeout(timer.current);
      setError(null);
      setStarting(true);
      try {
        const j = await starter();
        if (!alive.current) return;
        setJob(j);
        poll(j.id);
      } catch (e) {
        if (!alive.current) return;
        setJob(null);
        setError({ message: e instanceof Error ? e.message : String(e), code: e instanceof ProviderError ? e.code : undefined });
      } finally {
        if (alive.current) setStarting(false);
      }
    },
    [poll],
  );

  const cancel = useCallback(async () => {
    if (!job) return;
    if (timer.current) clearTimeout(timer.current);
    try {
      setJob(await provider.cancelJob(job.id));
    } catch (e) {
      setError({ message: e instanceof Error ? e.message : String(e) });
    }
  }, [job, provider]);

  const reset = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    setJob(null);
    setError(null);
  }, []);

  return { job, error, starting, start, cancel, reset };
}
