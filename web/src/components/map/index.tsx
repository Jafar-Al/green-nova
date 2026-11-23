"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/primitives";

/** MapLibre (~200 kB gzip) loads only on routes that show a map, and never during SSR. */
export const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => (
    <div className="grid size-full place-items-center bg-[#0b0f0d]" role="status" aria-label="Loading map">
      <Skeleton className="size-3/4 max-h-80 max-w-xl opacity-60" />
      <span className="visually-hidden">Loading map&hellip;</span>
    </div>
  ),
});

export type { MapViewProps, UnitCollection, UnitMapProps } from "./MapView";
