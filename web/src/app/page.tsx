import type { Metadata } from "next";
import { LandingHeader } from "@/components/landing/LandingHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { ClassSwatch, EvidenceBadge, LinkButton } from "@/components/ui/primitives";
import { SatPicture } from "@/components/ui/SatPicture";
import { IconArrowRight } from "@/components/ui/icons";
import { CLASS_LIST, EVIDENCE_META } from "@/lib/classes";
import { IS_DEMO_MODE, SITE_NAME, SITE_URL } from "@/lib/config";
import { EVIDENCE_VALUES } from "@/lib/contract";
import { DUNUM_DEFINITION } from "@/lib/units";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

const QUESTIONS = [
  "What currently prevents cultivation on this land?",
  "Can each limitation be reversed, partly or not at all?",
  "Which interventions fit the limitations found?",
  "How feasible is restoration, and how sure is the estimate?",
  "What suitability could be achieved afterwards?",
  "Which water resources and infrastructure would be required?",
  "Which crop categories could become viable?",
];

const STEPS = [
  { t: "Observe", d: "Sentinel-2 imagery and environmental layers for a governorate: terrain, rainfall, soil, water." },
  { t: "Classify", d: "Model 1 assigns every land unit one of five suitability classes, with a confidence value whose definition is stated." },
  { t: "Delineate", d: "Units become polygons with area in hectares and dunums and the factors behind each class." },
  { t: "Assess restoration", d: "Model 2 examines class 3 and 4 land: limits, reversibility, interventions and feasibility with an interval." },
  { t: "Decide and export", d: "Compare scenarios under your own water, time and feasibility constraints. Export GeoJSON, CSV or a report." },
];

const CAPABILITIES: [string, string][] = [
  ["Satellite map", "A real Sentinel-2 true-colour basemap with boundary, polygons, legend, scale and coordinates."],
  ["Governorate-wide analysis", "A whole governorate is analysed, not a single uploaded image. All 12 governorates of Jordan are covered."],
  ["Polygon inspection", "Click any land unit: class, area in hectares and dunums, confidence and the factors behind it."],
  ["Evidence labels", "Observed, ML-predicted, expert rule or simulated: stated on every factor, value and scenario."],
  ["Honest uncertainty", "Confidence with its definition, feasibility intervals, resolution limits and stated limitations."],
  ["Scenario comparison", "Interventions, water-requirement ranges, infrastructure, crop categories and time to effect side by side."],
  ["Your constraints", "Water available, water sources, time horizon, minimum feasibility: results re-rank instantly."],
  ["Exports", "GeoJSON, CSV and a printable report, each carrying its evidence classes and area-unit definition."],
];

const PREVIEW_ROWS: [string, string, string][] = [
  ["Satellite imagery", "Real", "Sentinel-2 L2A scenes, 25 February to 10 March 2026, true colour, resampled and mosaicked only."],
  ["Governorate boundary", "Real, coarse", "geoBoundaries gbOpen, a 2006 representation of Jordan’s governorates. Not a survey line."],
  ["Land polygons, classes, confidence, soil and terrain values", "Synthetic", "Generated locally for this preview. Positions are arbitrary and are not derived from the imagery."],
  ["Restoration scenarios, water ranges, interventions", "Synthetic, simulated by design", "Placeholders that exercise the interface. No source studies are attached."],
];

const LIVE_ROWS: [string, string, string][] = [
  ["Satellite imagery", "Real", "Sentinel-2 L2A scenes, 25 February to 10 March 2026, true colour, resampled and mosaicked only. A context layer: classes are not derived from it directly."],
  ["Governorate boundary", "Real, coarse", "geoBoundaries gbOpen, a 2006 representation of Jordan\u2019s governorates. Not a survey line."],
  ["Suitability polygons, classes, confidence, factors", "Model 1 output", "Each factor carries its evidence class. Spatial detail is limited to the effective resolution stated on every unit."],
  ["Restoration feasibility, limits, interventions", "Model 2 output", "Hybrid of ML soil prediction, FAO rules and Monte-Carlo feasibility with intervals."],
  ["Post-restoration class, water ranges, times", "Simulated", "Scenario outputs, never observed restoration results."],
];

export default function Landing() {
  const ld = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: SITE_URL,
    description: "Satellite land intelligence for agriculture: land suitability and restoration potential across all 12 governorates of Jordan.",
  };
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld) }} />

      {/* ============================ HERO ============================ */}
      <div className="theme-forest relative isolate overflow-hidden">
        <LandingHeader />
        <main id="main" tabIndex={-1} className="outline-none">
          <section aria-labelledby="hero-title" className="relative flex min-h-[max(34rem,calc(100svh-var(--demo-h)))] flex-col justify-end">
            <figure className="absolute inset-0 -z-10 m-0">
              <SatPicture
                name="hero-maan"
                widths={[800, 1600, 2400]}
                width={2400}
                height={1344}
                sizes="100vw"
                alt="Sentinel-2 true-colour satellite view near Al-Jafr in Ma’an Governorate, Jordan: dendritic wadi systems, a bright dry playa and small clusters of circular irrigated fields in the desert."
                priority
                className="hero-image size-full object-cover"
              />
              <div aria-hidden="true" className="absolute inset-0" style={{ background: "linear-gradient(90deg, rgb(8 19 13 / 0.9) 0%, rgb(8 19 13 / 0.74) 45%, rgb(8 19 13 / 0.34) 100%)" }} />
              <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-1/3" style={{ background: "linear-gradient(0deg, rgb(8 19 13 / 0.7), transparent)" }} />
            </figure>

            <div className="mx-auto w-full max-w-[84rem] px-[var(--spacing-gutter)] pb-10 pt-32 md:pb-14">
              <h1 id="hero-title" className="display m-0">
                <span className="hero-in block" style={{ ["--i" as string]: 0 }}>Discover.</span>
                <span className="hero-in block" style={{ ["--i" as string]: 1 }}>Restore.</span>
                <span className="hero-in block text-accent" style={{ ["--i" as string]: 2 }}>Grow.</span>
              </h1>
              <p className="lead hero-in mt-6 !text-ink" style={{ ["--i" as string]: 3 }}>
                GREEN NOVA AI maps where land is suitable for agriculture today and where degraded land could be restored, from satellite imagery, with the evidence behind every number in view.
              </p>
              <div className="hero-in mt-8 flex flex-wrap items-center gap-3" style={{ ["--i" as string]: 4 }}>
                <LinkButton href="/dashboard" variant="primary" size="lg">
                  Open the intelligence dashboard
                  <IconArrowRight className="size-5" />
                </LinkButton>
                <LinkButton href="#how" variant="secondary" size="lg">
                  How it works
                </LinkButton>
              </div>
              <p className="hero-in mt-6 max-w-[62ch] text-sm text-ink-2" style={{ ["--i" as string]: 5 }}>
                {IS_DEMO_MODE
                  ? "Preview: the dashboards currently show clearly labelled demonstration data while the trained models are being integrated."
                  : "Results come from the trained models. Every value carries its evidence class, and confidence is shown with its definition."}
              </p>
            </div>
            <figcaption className="border-t border-[#2b4b39] bg-[#0a1a12]/80 px-[var(--spacing-gutter)] py-2.5 text-xs text-ink-2">
              <span className="mx-auto block max-w-[84rem] font-mono">
                Sentinel-2 L2A &middot; true colour &middot; near Al-Jafr, Ma&rsquo;an Governorate, Jordan &middot; 2 and 7 Mar 2026 &middot; Contains modified Copernicus Sentinel data [2026]
              </span>
            </figcaption>
          </section>
        </main>
      </div>

      {/* ============================ INTRO ============================ */}
      <section className="theme-paper" aria-labelledby="intro-title">
        <div className="mx-auto grid max-w-[84rem] gap-10 px-[var(--spacing-gutter)] py-20 md:py-28 lg:grid-cols-[1.1fr_1fr] lg:gap-20">
          <h2 id="intro-title" className="h-section m-0">
            Know what land can do today, and what it could become.
          </h2>
          <div className="grid content-start gap-6">
            <p className="lead">
              Deciding where to farm, where to invest in reclamation and where not to touch the land usually means stitching together soil maps, imagery and rules of thumb. GREEN NOVA AI brings them into one map for a whole governorate.
            </p>
            <ul className="m-0 list-none divide-y divide-line border-y border-line p-0">
              {[
                ["Governorate-wide", "The unit of analysis is a region and its land polygons, not one uploaded image."],
                ["Every number carries its evidence", "Observed, ML-predicted, expert rule or simulated, shown beside each value."],
                ["Hectares and dunums", `Areas are computed in an equal-area projection. ${DUNUM_DEFINITION}.`],
              ].map(([t, d]) => (
                <li key={t} className="grid gap-1 py-4 sm:grid-cols-[13rem_1fr] sm:gap-6">
                  <span className="text-sm font-semibold text-ink">{t}</span>
                  <span className="text-sm text-ink-2">{d}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ============================ DISCOVER ============================ */}
      <section id="discover" className="theme-paper border-t border-line bg-sunken" aria-labelledby="discover-title" style={{ background: "var(--sunken)" }}>
        <div className="mx-auto grid max-w-[84rem] items-start gap-12 px-[var(--spacing-gutter)] py-20 md:py-28 lg:grid-cols-[1fr_1.05fr] lg:gap-20">
          <figure className="reveal m-0 grid gap-3">
            <div className="overflow-hidden rounded-md border border-line">
              <SatPicture name="discover" widths={[800, 1200]} width={1200} height={903} sizes="(min-width: 1024px) 40vw, 100vw" alt="Sentinel-2 true-colour close view near Al-Jafr, Ma’an: circular irrigated fields at the edge of a dry playa, surrounded by desert wadi fans." className="block h-auto w-full" />
            </div>
            <figcaption className="text-xs text-ink-3">Sentinel-2 L2A true colour, about 13 m per pixel (near Al-Jafr, 2 and 7 Mar 2026). Contains modified Copernicus Sentinel data [2026]. Context imagery only: it carries no classification.</figcaption>
          </figure>
          <div className="grid content-start gap-6">
            <h2 id="discover-title" className="h-section m-0">
              Discover where agriculture works today.
            </h2>
            <p className="lead">
              Model 1 classifies every land unit of a governorate into five classes and shows the factors behind each one: rainfall, soil salinity, pH, organic carbon, depth, slope, texture and water availability, plus legal or environmental restrictions.
            </p>
            <ul className="m-0 list-none divide-y divide-line border-y border-line p-0" aria-label="The five suitability classes">
              {CLASS_LIST.map((c) => (
                <li key={c.code} className="grid grid-cols-[auto_1fr] items-start gap-4 py-3.5">
                  <ClassSwatch code={c.code} />
                  <div>
                    <p className="m-0 text-sm font-semibold text-ink">{c.label}</p>
                    <p className="m-0 mt-0.5 text-sm text-ink-2">{c.description}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="m-0 text-sm text-ink-3">Each polygon reports area in hectares and dunums and a confidence value with its definition. Hatching marks excluded land so it never depends on colour alone.</p>
          </div>
        </div>
      </section>

      {/* ============================ RESTORE ============================ */}
      <section id="restore" className="theme-forest" aria-labelledby="restore-title">
        <div className="mx-auto grid max-w-[84rem] items-start gap-12 px-[var(--spacing-gutter)] py-20 md:py-28 lg:grid-cols-[1.05fr_1fr] lg:gap-20">
          <div className="grid content-start gap-6 lg:order-1">
            <h2 id="restore-title" className="h-section m-0">
              Restore what has been lost, with the uncertainty in view.
            </h2>
            <p className="lead">
              Model 2 looks at land that is not cultivable today and asks seven questions of each unit. It is a restoration potential assessment, not a generic recommendation engine.
            </p>
            <ul className="m-0 list-none divide-y divide-line border-y border-line p-0">
              {QUESTIONS.map((q) => (
                <li key={q} className="py-3 text-sm text-ink-2">
                  {q}
                </li>
              ))}
            </ul>
            <p className="m-0 text-sm text-ink-2">
              <strong className="text-ink">What is simulated.</strong> Post-restoration suitability, water requirements and intervention effects are expert-derived or simulated scenarios, shown as ranges and labelled as such. They are never presented as observed restoration results. Land excluded by a legal or environmental restriction is never treated as restorable.
            </p>
          </div>
          <figure className="reveal m-0 grid gap-3 lg:order-2">
            <div className="overflow-hidden rounded-md border border-line">
              <SatPicture name="restore" widths={[800, 1200]} width={1200} height={905} sizes="(min-width: 1024px) 40vw, 100vw" alt="Sentinel-2 true-colour view of wadi channels and scattered small fields in dry terrain in Ma’an, the kind of land where limiting factors are assessed." className="block h-auto w-full" />
            </div>
            <figcaption className="text-xs text-ink-3">Sentinel-2 L2A true colour, about 13 m per pixel (Ma&rsquo;an, 2 and 7 Mar 2026). Contains modified Copernicus Sentinel data [2026]. Context imagery only.</figcaption>
          </figure>
        </div>
      </section>

      {/* ============================ HOW IT WORKS ============================ */}
      <section id="how" className="theme-paper" aria-labelledby="how-title">
        <div className="mx-auto max-w-[84rem] px-[var(--spacing-gutter)] py-20 md:py-28">
          <h2 id="how-title" className="h-section m-0 max-w-[22ch]">
            From satellite pixels to a decision you can defend.
          </h2>
          <ol className="m-0 mt-12 grid list-none gap-0 border-t border-line-strong p-0 md:grid-cols-5">
            {STEPS.map((s, i) => (
              <li key={s.t} className="grid content-start gap-2 border-b border-line py-6 md:border-b-0 md:border-s md:px-5 md:first:border-s-0 md:first:ps-0">
                <span className="font-mono text-sm font-medium text-ink-3 tnum" aria-hidden="true">
                  {i + 1}
                </span>
                <h3 className="h-panel m-0 !text-lg">
                  <span className="visually-hidden">Step {i + 1}: </span>
                  {s.t}
                </h3>
                <p className="m-0 text-sm text-ink-2">{s.d}</p>
              </li>
            ))}
          </ol>
          <p className="mt-8 max-w-[70ch] text-sm text-ink-3">{IS_DEMO_MODE ? "In this preview, steps 2 and 4 are represented by demonstration data. The interface, the evidence labels and the exports are the real product surfaces." : "Steps 2 and 4 are the trained Model 1 and Model 2. Restoration outcomes remain simulated scenarios and are labelled as such."}</p>
        </div>
      </section>

      {/* ============================ CAPABILITIES ============================ */}
      <section className="theme-paper border-t border-line" aria-labelledby="cap-title" style={{ background: "var(--sunken)" }}>
        <div className="mx-auto grid max-w-[84rem] gap-10 px-[var(--spacing-gutter)] py-20 md:py-28 lg:grid-cols-[1fr_2fr] lg:gap-20">
          <h2 id="cap-title" className="h-section m-0">
            What the platform does.
          </h2>
          <dl className="m-0 grid gap-x-12 md:grid-cols-2">
            {CAPABILITIES.map(([t, d]) => (
              <div key={t} className="border-t border-line-strong py-4">
                <dt className="text-sm font-semibold text-ink">{t}</dt>
                <dd className="m-0 mt-1 text-sm text-ink-2">{d}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ============================ EVIDENCE ============================ */}
      <section id="evidence" className="theme-paper" aria-labelledby="evidence-title">
        <div className="mx-auto grid max-w-[84rem] gap-12 px-[var(--spacing-gutter)] py-20 md:py-28 lg:grid-cols-[1fr_1.2fr] lg:gap-20">
          <div className="grid content-start gap-6">
            <h2 id="evidence-title" className="h-section m-0">
              What is real, and what is not.
            </h2>
            <p className="lead">Every value in the product carries one of four evidence classes. Shape and text, not colour alone, tell them apart.</p>
            <ul className="m-0 grid list-none gap-4 p-0">
              {EVIDENCE_VALUES.map((e) => (
                <li key={e} className="grid gap-1.5 sm:grid-cols-[9rem_1fr] sm:gap-4">
                  <span>
                    <EvidenceBadge evidence={e} />
                  </span>
                  <span className="text-sm text-ink-2">{EVIDENCE_META[e].definition}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="grid content-start gap-4">
            <h3 className="h-panel !text-lg m-0">{IS_DEMO_MODE ? "What you see in this preview" : "What you see in the dashboards"}</h3>
            <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Preview status (scrollable table)">
              <table className="data-table">
                <caption className="visually-hidden">{IS_DEMO_MODE ? "Which parts of the preview are real and which are demonstration data" : "Which parts of the dashboards are real data, model output or simulated"}</caption>
                <thead>
                  <tr>
                    <th scope="col">Element</th>
                    <th scope="col">Status</th>
                    <th scope="col">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {(IS_DEMO_MODE ? PREVIEW_ROWS : LIVE_ROWS).map(([a, b, c]) => (
                    <tr key={a}>
                      <th scope="row" className="!border-b !border-line !px-3 !py-3 !text-sm !normal-case !tracking-normal !text-ink">
                        {a}
                      </th>
                      <td className="font-semibold text-ink">{b}</td>
                      <td className="text-ink-2">{c}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="m-0 text-sm text-ink-2">
              {IS_DEMO_MODE ? (
                <>
                  Every page that shows demonstration data carries the marker <strong className="text-ink">DEMONSTRATION DATA &mdash; not a model prediction</strong>, and so does every file exported from it.
                </>
              ) : (
                <>Exports carry the same evidence classes and the area-unit definition, so a file read outside the site keeps its context.</>
              )}
            </p>
          </div>
        </div>
      </section>

      {/* ============================ CTA ============================ */}
      <section className="theme-forest" aria-labelledby="cta-title">
        <div className="mx-auto grid max-w-[84rem] items-end gap-8 px-[var(--spacing-gutter)] py-20 md:py-24 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <h2 id="cta-title" className="h-section m-0">
              Start with Ma&rsquo;an, Jordan.
            </h2>
            <p className="lead mt-4">Open the dashboard to explore the map, run a suitability analysis, select unsuitable land and compare restoration scenarios.</p>
          </div>
          <div className="flex flex-wrap gap-3 lg:justify-end">
            <LinkButton href="/dashboard" variant="primary" size="lg">
              Open the intelligence dashboard
              <IconArrowRight className="size-5" />
            </LinkButton>
            <LinkButton href="/suitability" variant="secondary" size="lg">
              Run a suitability analysis
            </LinkButton>
          </div>
        </div>
      </section>
      <SiteFooter />
    </>
  );
}
