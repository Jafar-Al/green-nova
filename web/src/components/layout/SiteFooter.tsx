import Link from "next/link";
import { Logo } from "@/components/brand/Logo";
import { BOUNDARY_ATTRIBUTION, IS_DEMO_MODE } from "@/lib/config";
import { DUNUM_DEFINITION } from "@/lib/units";

const NAV: [string, string][] = [
  ["/dashboard", "Intelligence dashboard"],
  ["/suitability", "Land suitability"],
  ["/restoration", "Restoration potential"],
];

export function SiteFooter() {
  return (
    <footer className="theme-forest border-t border-line">
      <div className="mx-auto grid max-w-[84rem] gap-10 px-[var(--spacing-gutter)] py-12 md:grid-cols-[1.2fr_1fr_1.6fr]">
        <div className="grid content-start gap-3">
          <Logo cut="#0f2419" />
          <p className="m-0 text-sm text-ink-2">Discover. Restore. Grow.</p>
        </div>
        <nav aria-label="Footer" className="grid content-start gap-1">
          <p className="label mb-1">Workspaces</p>
          {NAV.map(([href, label]) => (
            <Link key={href} href={href} className="inline-flex min-h-9 items-center text-sm text-ink-2 hover:text-ink">
              {label}
            </Link>
          ))}
        </nav>
        <div className="grid content-start gap-2 text-xs text-ink-3">
          <p className="label mb-1">Data and attribution</p>
          <p className="m-0">Satellite imagery: Contains modified Copernicus Sentinel data [2026]. Sentinel-2 L2A, true colour, rendered by GREEN NOVA AI.</p>
          <p className="m-0">{BOUNDARY_ATTRIBUTION} (Runfola et al., 2020; Jordan ADM1 boundaries from Wikimedia Commons). The boundary is coarse and is not a survey line.</p>
          <p className="m-0">{DUNUM_DEFINITION}. Areas are computed in an equal-area projection.</p>
          {IS_DEMO_MODE ? <p className="m-0">Preview build: the dashboards show clearly labelled demonstration data, not model predictions.</p> : null}
        </div>
      </div>
    </footer>
  );
}
