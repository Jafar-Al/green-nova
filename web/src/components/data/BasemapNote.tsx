import { BASEMAP, IS_DEMO_MODE } from "@/lib/config";
import { Disclosure } from "@/components/ui/primitives";

/** Honest statement of what the basemap is and how much detail it can carry (never more precision than the source). */
export function BasemapNote() {
  const selfHosted = BASEMAP.tileUrl.startsWith("/tiles/s2");
  return (
    <Disclosure summary="About the satellite basemap" className="rounded-sm border border-line px-3">
      <p className="m-0 text-xs text-ink-2">
        {selfHosted ? (
          <>
            True-colour mosaic rendered from Sentinel-2 L2A scenes acquired 25 February to 10 March 2026, shown at up to about 66 m per pixel (zoom 11).
            Zooming in further enlarges the pixels and adds no detail. It is a context layer: {IS_DEMO_MODE ? "the polygons are not derived from it in this demonstration." : "unit classes come from the models' own inputs, not from this image."}
          </>
        ) : (
          <>Basemap supplied by the configured satellite tile source. Check its resolution and licence terms before relying on it.</>
        )}
      </p>
      <p className="mt-1.5 text-xs text-ink-3">{BASEMAP.attribution}.</p>
    </Disclosure>
  );
}
