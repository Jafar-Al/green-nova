# GREEN NOVA AI design system (web, Phase A)

Source of truth for tokens: `web/src/app/globals.css` (CSS variables + Tailwind v4 `@theme`). Colour contrast of every role pair is
verified by `web/src/lib/__tests__/contrast.test.ts` (parses the CSS, fails the build on regression).

## Direction
A serious geospatial-intelligence product, not a SaaS template. Deep forest green (brand), forest-tinted charcoal (workspace),
warm off-white (reading), restrained natural-green accent. Real Sentinel-2 imagery is the only imagery; no illustrations, no
gradients on controls, no glass, no cards-with-icons as page structure. Structure comes from hairlines and spacing.
- **App surfaces = dark charcoal** (analysts read imagery in dim rooms; the map must be the brightest thing). Landing mixes
  deep forest (hero, restoration, CTA) with warm paper (reading sections).
- Fonts: **Archivo** (variable, width axis; display set at 106-114 % width, weight 560-640) for everything, **JetBrains Mono** only for
  ids, coordinates and imagery captions (measurement/data). Self-hosted at build time by `next/font` (OFL licences).
- Display faces on the "avoid" list (Fraunces, Playfair, Inter-as-display, ...) were not used.

## Theme scopes (roles, not colours)
Apply one class to a surface: `.theme-dark` (app), `.theme-paper` (reading), `.theme-forest` (brand bands). Utilities use roles:
`bg-canvas | bg-surface | bg-raised | bg-sunken`, `text-ink | text-ink-2 | text-ink-3`, `border-line | border-line-strong`,
`bg-accent text-on-accent`, `text-danger | text-warn | text-ok`, focus ring `--focus`. Semantic roles are declared with
`@theme inline` (they point at scope variables); primitives are in `@theme`.

| Role | dark | paper | forest |
|---|---|---|---|
| canvas | #101412 | #f5f2ea | #0f2419 |
| surface | #171c19 | #fbf9f4 | #153324 |
| ink / ink-2 / ink-3 | #f1eee6 / #c5ccc4 / #98a39b | #141a16 / #3f4842 / #566058 | #f1eee6 / #c9d5cb / #9fb4a4 |
| line-strong (controls, >= 3:1) | #66746b | #7e867c | #6f8c78 |
| accent / on-accent | #a3c98f / #0b170f | #1d4533 / #f5f2ea | #a3c98f / #0a1a12 |

Primitives: forest 950-500, moss 300-700 (accent family), charcoal 950-200, paper 50-400, sand-300/500 and clay-500 (signal only).
Verified: ink >= 7:1, ink-2/ink-3/accent >= 4.5:1 on every surface, line-strong and focus >= 3:1, state colours >= 4.5:1.

## Data colours (meaning, not decoration)
- **Suitability classes** (`web/src/lib/classes.ts`): 1 `#2d9a63`, 2 `#a8c256`, 3 `#e3a43a`, 4 `#b8572e`, 5 `#7a89b4` + hatch.
  The class **number is printed on every swatch** and excluded land is **hatched**: colour is never the only cue.
- **Restoration feasibility** (blue-teal ramp, kept distinct from the green/amber suitability ramp): high `#246d9c`, moderate `#4aa6b8`,
  low `#9ed2d6`, not feasible `#64707a`.
- **Confidence overlay**: 4-step single-hue ramp (`layers.ts`), bins stated in the legend.
- **Simulated outcomes**: dashed outline + hatch on the map; "Simulated" evidence badge with dashed border everywhere.
- **Evidence classes** (observed / ML-predicted / expert rule / simulated): distinct glyph shape + text + border style, never colour.
- Basemap is muted (`raster-saturation -0.32`, `brightness-max 0.78`) so overlays read on bright desert imagery.

## Type scale
Fixed rem scale for the app (product UI), fluid only for landing display. Body 16 px, UI 14 px, captions 12 px (nothing smaller).
| Role | Size | Notes |
|---|---|---|
| `.display` | clamp(3.1rem, 9.2vw, 6rem) | hero only; width 114 %, tracking -0.028em, lh 0.96 |
| `.h-section` | clamp(2rem, 4.6vw, 3.5rem) | landing section headings; width 108 % |
| `.h-page` | clamp(1.6rem, 3vw, 2.25rem) | page titles |
| `.h-panel` | 1rem / 620 | panel headings |
| `.lead` | clamp(1.0625rem, 1.5vw, 1.25rem) | max 60ch |
| `.label` | 0.75rem upper, 0.04em | table headers, field group labels |
| body / `text-sm` / `text-xs` | 1rem / 0.875rem / 0.75rem | `.tnum` for tabular numerals |
Prose measure <= 68ch (`.measure`); headings `text-wrap: balance`.

## Spacing, shape, depth, motion
- 4 px base (Tailwind scale); page gutter `--spacing-gutter` clamp(1rem, 4vw, 2.5rem); sections 5-7 rem vertical.
- Radii 2/4/6/10 px (restrained). Depth = hairlines + one soft offset shadow on floating map UI; no halos, no hard offset shadows.
- Motion personality: **Corporate/Premium**. Easings `--ease-out` cubic-bezier(.16,1,.3,1), `--ease-standard` cubic-bezier(.2,0,0,1);
  durations 120 / 200 / 420 ms. One authored moment: the hero (image settles 1.4 s, headline lines stagger <= 0.6 s total).
  Product surfaces animate state only (job progress, disclosure chevron, press feedback). Scroll reveal is progressive
  (`animation-timeline: view()`) and only on two figures. `prefers-reduced-motion` removes all of it; MapLibre `fadeDuration` and
  `fitBounds` durations drop to 0.
- Browser surfaces themed: selection, caret, `accent-color`, thin scrollbars, MapLibre controls/attribution/scale, `color-scheme`.

## Layout
Workspaces are a three-column grid at >= 1024 px (`controls | map | results`, named areas, each side column scrolls independently),
stacked below that with the map first (62 dvh). Landing max width 84 rem. Logical properties throughout (`ms-`, `ps-`, `border-s`,
`inset-inline-*`, `text-align: start/end`) so RTL is feasible; `dir="ltr"` is set on `<html>` for now. `.grid > * { min-width: 0 }`
prevents wide tables from stretching columns; every table that can overflow sits in a focusable, labelled scroll region.

## Components (web/src/components)
| Group | Components |
|---|---|
| ui | Button, LinkButton (primary/secondary/ghost x sm/md/lg), Segmented (radio group), CheckRow, FieldLabel, Disclosure, Meter, Skeleton, KV, ClassSwatch, ClassChip, EvidenceBadge, FactorStatusBadge, EmptyState, ErrorState, OfflineBanner, DemoNote, DemoMapMarker, LoadingLine, SatPicture, icons (one 24 px / 1.6 stroke family) |
| layout | DemoBar (sticky, all routes), AppHeader, SiteFooter, LandingHeader |
| map | MapView (MapLibre, client-only, lazy), MapLegend, mapStyle |
| data | RegionSelectors, AreaStats, FilterPanel, PolygonList, PolygonDetail, FactorList, ProbabilityBars, JobStatusPanel, ExportPanel, BasemapNote, RestorationParts (ConstraintsForm, ScenarioCompare, OutcomeComparison, LimitingFactorList, InterventionList, WaterRange, FeasibilityChip) |
| views | DashboardView, SuitabilityView, RestorationView, LandView |

Every interactive component ships default / hover (pointer devices only) / focus-visible / active / disabled; async components add
loading (skeleton), empty, error (with retry) and offline states. Forms use visible labels and helper text. Disabled export formats
stay visible with the reason.

## Accessibility rules in force
WCAG 2.2 AA: skip link first, landmarks on every route, one `h1`, focus ring 2 px (>= 3:1), target size >= 24 px (controls 40 px),
`aria-live` for job state, `role=progressbar|meter` with text values, keyboard-reachable list as the alternative to map clicking,
reduced motion, 360 px reflow without horizontal page scroll, no information by colour alone.

## Honesty rules in the UI
1. Persistent amber `DEMONSTRATION DATA — not a model prediction` bar on every route (sticky), repeated inside every map and in every
   exported file. Driven by `NEXT_PUBLIC_DATA_PROVIDER` (anything but `api` shows it).
2. Never present synthetic output as a model result; copy says "demonstration", "synthetic", "simulated".
3. Confidence always shown with its per-record definition; never labelled accuracy.
4. Units: ha and dunum together, with `1 dunum = 1,000 m2 = 0.1 ha` stated.
5. Resolution limits stated (basemap ~66 m/pixel, unit effective resolution).

## Skills
Applied: impeccable (direction + craft floor; its launcher script was not present in the skill folder, context was read directly),
anti-slop, ui-ux-pro-max (its design-system query returned an off-topic indigo/orange match and was not used; palette is brief-driven),
design-system, accessibility, motion-design, core-web-vitals, best-practices. `frontend-design` and `karpathy-guidelines` are not installed.
