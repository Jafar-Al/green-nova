import { IS_DEMO_MODE } from "@/lib/config";
import { Disclosure } from "@/components/ui/primitives";

/**
 * Mandatory caveats on every REAL Model 2 view (product requirement). Not shown for demonstration data, which has its own marker.
 * Static text; the numbers named here are the documented defaults in docs/MODEL2_RESTORATION.md.
 */
export function Model2Caveats({ className = "" }: { className?: string }) {
  if (IS_DEMO_MODE) return null;
  return (
    <aside aria-label="How to read restoration results" className={`grid gap-1.5 rounded-sm border border-warn/60 p-3 text-xs text-ink-2 ${className}`}>
      <p className="m-0 text-ink">
        <strong>Read these results as conditional.</strong> Feasibility assumes a reference water allocation (8,000 m&sup3;/ha/yr by default). It means &ldquo;technically feasible if water is supplied&rdquo;. Water source availability, quality and aquifer
        sustainability are not mapped, and most cells therefore come out highly feasible.
      </p>
      <Disclosure summary="More caveats" className="rounded-sm border border-line px-3">
        <ul className="m-0 grid list-disc gap-1 ps-4 text-xs text-ink-2">
          <li>Soil salinity and sodicity are ML-predicted with weak skill on held-out geography and wide intervals: treat them as regional priors, not measurements.</li>
          <li>Post-restoration suitability, water requirements, intervention effects and times are <strong>simulated</strong> scenarios with ranges. They are never observed restoration results; no before-and-after data exists.</li>
          <li>Effective spatial resolution is about 1 to 4 km: do not read sub-kilometre polygon values as measurements.</li>
          <li>Wind erosion, flash floods, frost and economics are not modelled. Each field carries its evidence class: observed, ML-predicted, expert rule or simulated.</li>
        </ul>
      </Disclosure>
    </aside>
  );
}
