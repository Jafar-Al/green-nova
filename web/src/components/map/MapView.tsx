"use client";

import maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MLMap, MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Feature, FeatureCollection, Geometry, Polygon, Position } from "geojson";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { BASEMAP, BOUNDARY_ATTRIBUTION } from "@/lib/config";
import { geometryBBox, unionBBox, type BBox } from "@/lib/geo";
import { useOnline, usePrefersReducedMotion } from "@/lib/hooks";
import { DemoMapMarker } from "@/components/ui/states";
import { IconAlert, IconOffline } from "@/components/ui/icons";
import { buildStyle, makeHatchImage } from "./mapStyle";

/** Properties MapView reads from each unit feature. Everything else is ignored. */
export interface UnitMapProps {
  id: string;
  /** Fill colour (hex). */
  fill: string;
  /** Hatch overlay (excluded land, simulated outcomes). */
  hatch?: boolean;
  /** Dashed outline (simulated outcomes). */
  dashed?: boolean;
  /** Muted: out of scope for the current view. */
  dim?: boolean;
}
export type UnitCollection = FeatureCollection<Geometry, UnitMapProps>;

export interface MapViewProps {
  boundary?: Feature<Geometry> | null;
  units?: UnitCollection | null;
  selectedIds?: string[];
  /** Fit the viewport to this box whenever it changes (identity-compared via JSON). */
  fitTo?: BBox | null;
  /** Fly to this unit when it changes. */
  focusId?: string | null;
  onSelect?: (id: string, opts: { additive: boolean }) => void;
  onBackgroundClick?: () => void;
  getTooltip?: (id: string) => string | null;
  ariaLabel: string;
  /** Overlays placed under the demonstration marker (legend, layer notes). */
  overlay?: ReactNode;
  /** false => static locator map (no pan/zoom/clicks). */
  interactive?: boolean;
  className?: string;
  /** Dim the basemap (helps overlays read on bright desert imagery). 0..1 */
  basemapDim?: number;
  showControls?: boolean;
}

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

function worldMask(boundary: Feature<Geometry> | null | undefined): FeatureCollection {
  if (!boundary) return EMPTY;
  const g = boundary.geometry;
  const outers: Position[][] = g.type === "Polygon" ? [g.coordinates[0] as Position[]] : g.type === "MultiPolygon" ? g.coordinates.map((p) => p[0] as Position[]) : [];
  if (outers.length === 0) return EMPTY;
  const world: Position[] = [
    [-180, -85],
    [180, -85],
    [180, 85],
    [-180, 85],
    [-180, -85],
  ];
  const poly: Polygon = { type: "Polygon", coordinates: [world, ...outers] };
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: poly }] };
}

function unitsBBox(units: UnitCollection | null | undefined, id: string): BBox | null {
  const f = units?.features.find((x) => x.properties.id === id);
  return f ? geometryBBox(f.geometry) : null;
}

export default function MapView({
  boundary,
  units,
  selectedIds = [],
  fitTo,
  focusId,
  onSelect,
  onBackgroundClick,
  getTooltip,
  ariaLabel,
  overlay,
  interactive = true,
  className = "",
  basemapDim = 0,
  showControls = true,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const loadedRef = useRef(false);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [tileErrors, setTileErrors] = useState(0);
  const coordRef = useRef<HTMLOutputElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const prevSelected = useRef<Set<string>>(new Set());
  const hoverId = useRef<string | null>(null);
  const online = useOnline();
  const reduced = usePrefersReducedMotion();
  const reducedRef = useRef(reduced);

  // latest callbacks without re-binding map listeners
  const cb = useRef({ onSelect, onBackgroundClick, getTooltip });

  const selectedIdsRef = useRef<string[]>(selectedIds);

  // keep the refs read by map listeners current (assigned in an effect, never during render)
  useEffect(() => {
    reducedRef.current = reduced;
    cb.current = { onSelect, onBackgroundClick, getTooltip };
    selectedIdsRef.current = selectedIds;
  });

  const maskData = useMemo(() => worldMask(boundary), [boundary]);
  const boundaryData = useMemo<FeatureCollection>(() => (boundary ? { type: "FeatureCollection", features: [boundary as Feature] } : EMPTY), [boundary]);

  /* ---- init once ---- */
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let map: MLMap;
    try {
      map = new maplibregl.Map({
        container: el,
        style: buildStyle(true),
        center: [36.7, 30.2],
        zoom: 6,
        minZoom: BASEMAP.minZoom - 1,
        maxZoom: BASEMAP.maxZoom + 3,
        attributionControl: false,
        interactive,
        cooperativeGestures: interactive && window.innerWidth < 1024,
        maxBounds: [
          [BASEMAP.bounds[0] - 0.7, BASEMAP.bounds[1] - 0.6],
          [BASEMAP.bounds[2] + 0.7, BASEMAP.bounds[3] + 0.6],
        ],
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        fadeDuration: reducedRef.current ? 0 : 150,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "WebGL is not available";
      const t = setTimeout(() => setFailed(msg), 0);
      return () => clearTimeout(t);
    }
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    if (interactive && showControls) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 110 }), "bottom-left");
    }
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: BOUNDARY_ATTRIBUTION }), "bottom-right");

    map.on("load", () => {
      map.addImage("hatch", makeHatchImage());
      map.addSource("mask", { type: "geojson", data: EMPTY });
      map.addSource("boundary", { type: "geojson", data: EMPTY });
      map.addSource("units", { type: "geojson", data: EMPTY, promoteId: "id" });
      map.addLayer({ id: "dim", type: "background", paint: { "background-color": "#050806", "background-opacity": 0 } });
      map.addLayer({ id: "mask-fill", type: "fill", source: "mask", paint: { "fill-color": "#050806", "fill-opacity": 0.5 } });
      map.addLayer({
        id: "units-fill",
        type: "fill",
        source: "units",
        paint: {
          "fill-color": ["get", "fill"],
          "fill-opacity": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            0.86,
            ["boolean", ["get", "dim"], false],
            0.12,
            ["boolean", ["feature-state", "hover"], false],
            0.86,
            0.7,
          ],
        },
      });
      map.addLayer({
        id: "units-hatch",
        type: "fill",
        source: "units",
        filter: ["all", ["==", ["get", "hatch"], true], ["!=", ["get", "dim"], true]],
        paint: { "fill-pattern": "hatch", "fill-opacity": 0.9 },
      });
      map.addLayer({
        id: "units-line",
        type: "line",
        source: "units",
        filter: ["!=", ["get", "dashed"], true],
        paint: { "line-color": "#f4f1e8", "line-opacity": ["case", ["boolean", ["get", "dim"], false], 0.28, 0.85], "line-width": 1.1 },
      });
      map.addLayer({
        id: "units-line-dashed",
        type: "line",
        source: "units",
        filter: ["==", ["get", "dashed"], true],
        paint: { "line-color": "#f4f1e8", "line-opacity": 0.95, "line-width": 1.4, "line-dasharray": [2.2, 1.6] },
      });
      map.addLayer({
        id: "units-selected-casing",
        type: "line",
        source: "units",
        paint: { "line-color": "#050806", "line-opacity": 0.85, "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 6, 0] },
      });
      map.addLayer({
        id: "units-selected",
        type: "line",
        source: "units",
        paint: { "line-color": "#ffffff", "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.6, 0] },
      });
      map.addLayer({ id: "boundary-casing", type: "line", source: "boundary", paint: { "line-color": "#050806", "line-opacity": 0.55, "line-width": 4.5 } });
      map.addLayer({ id: "boundary-line", type: "line", source: "boundary", paint: { "line-color": "#cfe8c3", "line-width": 1.7, "line-dasharray": [3, 2] } });
      loadedRef.current = true;
      setReady(true);
    });

    map.on("error", (e) => {
      const ev = e as unknown as { sourceId?: string; error?: { message?: string } };
      if (ev.sourceId === "sat") setTileErrors((n) => n + 1);
    });
    map.on("sourcedata", (e) => {
      if (e.sourceId === "sat" && e.isSourceLoaded) setTileErrors(0);
    });

    if (interactive) {
      map.on("mousemove", (e: MapMouseEvent) => {
        if (coordRef.current) coordRef.current.textContent = `${e.lngLat.lat.toFixed(4)}° N  ${e.lngLat.lng.toFixed(4)}° E`;
      });
      map.on("mousemove", "units-fill", (e) => {
        map.getCanvas().style.cursor = "pointer";
        const id = e.features?.[0]?.properties?.id as string | undefined;
        if (!id) return;
        if (hoverId.current !== id) {
          if (hoverId.current) map.setFeatureState({ source: "units", id: hoverId.current }, { hover: false });
          map.setFeatureState({ source: "units", id }, { hover: true });
          hoverId.current = id;
        }
        const tip = tipRef.current;
        const text = cb.current.getTooltip?.(id);
        if (tip && text) {
          tip.textContent = text;
          tip.style.display = "block";
          const w = el.clientWidth;
          const x = Math.min(e.point.x + 14, w - tip.offsetWidth - 8);
          tip.style.transform = `translate(${Math.max(8, x)}px, ${e.point.y + 14}px)`;
        }
      });
      map.on("mouseleave", "units-fill", () => {
        map.getCanvas().style.cursor = "";
        if (hoverId.current) map.setFeatureState({ source: "units", id: hoverId.current }, { hover: false });
        hoverId.current = null;
        if (tipRef.current) tipRef.current.style.display = "none";
      });
      map.on("click", (e) => {
        const hit = map.queryRenderedFeatures(e.point, { layers: ["units-fill"] })[0];
        const id = hit?.properties?.id as string | undefined;
        if (id) cb.current.onSelect?.(id, { additive: e.originalEvent.shiftKey || e.originalEvent.ctrlKey || e.originalEvent.metaKey });
        else cb.current.onBackgroundClick?.();
      });
    }

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      loadedRef.current = false;
      setReady(false);
      map.remove();
      mapRef.current = null;
      prevSelected.current = new Set();
      hoverId.current = null;
    };
    // map is created once per mount; props are synced by the effects below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- data sync ---- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("mask") as GeoJSONSource | undefined)?.setData(maskData);
    (map.getSource("boundary") as GeoJSONSource | undefined)?.setData(boundaryData);
  }, [ready, maskData, boundaryData]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("units") as GeoJSONSource | undefined)?.setData(units ?? EMPTY);
    // feature state is keyed by id; re-assert selection after the source reloads
    prevSelected.current = new Set();
    const src = map.getSource("units");
    if (src) for (const id of selectedIdsRef.current) map.setFeatureState({ source: "units", id }, { selected: true });
    prevSelected.current = new Set(selectedIdsRef.current);
  }, [ready, units]);

  const selKey = selectedIds.join("|");
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const next = new Set(selectedIds);
    for (const id of prevSelected.current) if (!next.has(id)) map.setFeatureState({ source: "units", id }, { selected: false });
    for (const id of next) if (!prevSelected.current.has(id)) map.setFeatureState({ source: "units", id }, { selected: true });
    prevSelected.current = next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, selKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setPaintProperty("dim", "background-opacity", basemapDim);
  }, [ready, basemapDim]);

  /* ---- viewport ---- */
  const fitKey = fitTo ? fitTo.join(",") : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !fitTo) return;
    map.fitBounds(
      [
        [fitTo[0], fitTo[1]],
        [fitTo[2], fitTo[3]],
      ],
      { padding: 36, duration: reducedRef.current ? 0 : 800, maxZoom: BASEMAP.maxZoom + 2 },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, fitKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !focusId) return;
    const b = unitsBBox(units, focusId);
    if (!b) return;
    const full = unionBBox([b]) as BBox;
    map.fitBounds(
      [
        [full[0], full[1]],
        [full[2], full[3]],
      ],
      { padding: { top: 60, bottom: 60, left: 60, right: 60 }, duration: reducedRef.current ? 0 : 700, maxZoom: 11.5 },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, focusId]);

  const basemapBroken = tileErrors >= 4;

  return (
    <div className={`relative isolate overflow-hidden bg-[#0b0f0d] ${className}`}>
      <div className="absolute inset-0">
        <div ref={containerRef} role="region" aria-label={ariaLabel} aria-describedby={interactive ? "map-keys-hint" : undefined} className="size-full" />
      </div>
      {interactive ? (
        <p id="map-keys-hint" className="visually-hidden">
          Map. With the map focused, arrow keys pan and plus or minus zoom. Land units can also be chosen from the list next to the map.
        </p>
      ) : null}

      <div className="pointer-events-none absolute start-2 top-2 z-10 flex max-w-[calc(100%-4.25rem)] flex-col items-start gap-2">
        <DemoMapMarker />
        <div className="pointer-events-auto">{overlay}</div>
      </div>

      {interactive ? (
        <>
          <output
            ref={coordRef}
            aria-hidden="true"
            className="pointer-events-none absolute bottom-9 start-2 z-10 hidden rounded-xs bg-[color-mix(in_oklab,var(--canvas)_78%,transparent)] px-1.5 py-0.5 font-mono text-xs text-ink-2 md:block"
          />
          <div
            ref={tipRef}
            aria-hidden="true"
            className="pointer-events-none absolute start-0 top-0 z-20 hidden max-w-64 rounded-xs border border-line-strong bg-canvas px-2 py-1 text-xs text-ink shadow-[0_6px_16px_rgb(0_0_0/0.45)]"
          />
        </>
      ) : null}

      {failed ? (
        <div role="alert" className="absolute inset-0 z-30 grid place-items-center bg-canvas/90 p-6 text-center">
          <div className="max-w-sm">
            <IconAlert className="mx-auto size-6 text-danger" />
            <h3 className="h-panel mt-2 text-ink">The map could not start</h3>
            <p className="mt-1 text-sm text-ink-2">
              This browser or device could not create a WebGL map. All land units remain available in the list and in each unit&rsquo;s detail panel.
            </p>
            <p className="mt-1 text-xs text-ink-3">{failed}</p>
          </div>
        </div>
      ) : null}

      {(basemapBroken || !online) && !failed ? (
        <p
          role="status"
          className="absolute inset-x-2 bottom-12 z-20 mx-auto flex max-w-md items-start gap-2 rounded-sm border border-warn/70 bg-canvas/95 px-3 py-2 text-xs text-ink-2 md:bottom-10"
        >
          {online ? <IconAlert className="mt-0.5 size-4 shrink-0 text-warn" /> : <IconOffline className="mt-0.5 size-4 shrink-0 text-warn" />}
          <span>
            <strong className="text-ink">{online ? "Satellite basemap unavailable." : "Offline."}</strong> Boundaries and land units still render on the dark background.
            {online ? " The tile source could not be reached or has no tiles here." : " Tiles already cached may still show."}
          </span>
        </p>
      ) : null}
    </div>
  );
}
