/**
 * Synthetic Ma'an-shaped demonstration data (Phase A). Deterministic for a given seed.
 *
 * What is real here: the governorate boundary (geoBoundaries) used to keep polygons inside Ma'an.
 * What is synthetic: EVERYTHING else - polygon positions, shapes, classes, soil/terrain/climate values, confidence,
 * interventions, scenarios and water ranges. No model produced any of it.
 * The structure follows docs/CONTRACT.md exactly so the same UI can render real model output in Phase C.
 */
import type { Position } from "geojson";
import type {
  ClassKey,
  Evidence,
  FactorStatus,
  Feasibility,
  FeasibilityClass,
  Intervention,
  LimitingFactor,
  MeasuredValue,
  RestorationCollection,
  RestorationFeature,
  RestorationScenario,
  Reversibility,
  SuitabilityClassCode,
  SuitabilityCollection,
  SuitabilityFactor,
  SuitabilityFeature,
} from "../contract";
import { SUITABILITY_CLASSES } from "../classes";
import { KM_PER_DEG_LAT, kmPerDegLon, pointInRing, polygonAreaM2, ringBBox, round6 } from "../geo";
import { m2ToDunum, m2ToHa, roundArea } from "../units";
import { DEMO_CONFIDENCE_METHOD, DEMO_MODEL_VERSION, DEMO_SOURCE_LABEL } from "./notice";
import { clamp, mulberry32, normal, pick, round, shuffle, uniform, type Rng } from "./prng";

export interface GenerateOptions {
  /** e.g. "jo-maan" */
  regionId: string;
  /** Outer ring of the region boundary, lon/lat. */
  ring: Position[];
  seed?: number;
  /** Number of land units. */
  count?: number;
  /** Provide for deterministic output in tests; defaults to the current time. */
  now?: string;
}

export interface DemoDataset {
  regionId: string;
  seed: number;
  createdAt: string;
  suitability: SuitabilityCollection;
  /** Model 2 results for every class 3 and 4 unit (the UI filters to the user's selection). */
  restoration: RestorationCollection;
}

/* ------------------------------------------------------------------ factor catalogue */

type Band = "favourable" | "marginal" | "limiting";

interface FactorSpec {
  name: string;
  unit: string;
  category: "water" | "soil" | "terrain" | "vegetation";
  evidence: Evidence;
  digits: number;
  importance: number;
  /** null = a symptom, not a causal limiting factor (excluded from Model 2 limiting_factors). */
  reversibility: ((v: number) => Reversibility) | null;
  irreversible: boolean;
  sample: Record<Band, (r: Rng) => number>;
  classify: (v: number) => Band;
  /** 0..1 how far into the limiting range the value is. */
  overshoot: (v: number) => number;
  rule: string;
}

const lerpClamp = (v: number, a: number, b: number): number => clamp((v - a) / (b - a), 0, 1);

const FACTORS: FactorSpec[] = [
  {
    name: "rainfall",
    unit: "mm/yr",
    category: "water",
    evidence: "observed",
    digits: 0,
    importance: 0.18,
    reversibility: () => "irreversible",
    irreversible: true,
    sample: { favourable: (r) => uniform(r, 160, 320), marginal: (r) => uniform(r, 90, 160), limiting: (r) => uniform(r, 28, 90) },
    classify: (v) => (v >= 160 ? "favourable" : v >= 90 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(90 - v, 0, 62),
    rule: "demo rule: limiting below 90 mm/yr, favourable from 160 mm/yr",
  },
  {
    name: "soil_salinity_ec",
    unit: "dS/m",
    category: "soil",
    evidence: "ml_predicted",
    digits: 1,
    importance: 0.16,
    reversibility: (v) => (v > 15 ? "partially_reversible" : "reversible"),
    irreversible: false,
    sample: {
      favourable: (r) => uniform(r, 0.4, 2),
      marginal: (r) => uniform(r, 2, 4),
      limiting: (r) => clamp(4 + Math.abs(normal(r, 0, 6)), 4, 24),
    },
    classify: (v) => (v < 2 ? "favourable" : v < 4 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(v, 4, 20),
    rule: "demo rule: limiting from 4 dS/m, favourable below 2 dS/m",
  },
  {
    name: "soil_ph",
    unit: "",
    category: "soil",
    evidence: "ml_predicted",
    digits: 1,
    importance: 0.08,
    reversibility: () => "partially_reversible",
    irreversible: false,
    sample: { favourable: (r) => uniform(r, 7.2, 8.2), marginal: (r) => uniform(r, 8.2, 8.6), limiting: (r) => uniform(r, 8.6, 9.3) },
    classify: (v) => (v <= 8.2 ? "favourable" : v <= 8.6 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(v, 8.6, 9.4),
    rule: "demo rule: limiting above pH 8.6, favourable up to pH 8.2",
  },
  {
    name: "soil_organic_carbon",
    unit: "%",
    category: "soil",
    evidence: "ml_predicted",
    digits: 2,
    importance: 0.1,
    reversibility: () => "reversible",
    irreversible: false,
    sample: { favourable: (r) => uniform(r, 0.6, 1.4), marginal: (r) => uniform(r, 0.3, 0.6), limiting: (r) => uniform(r, 0.05, 0.3) },
    classify: (v) => (v >= 0.6 ? "favourable" : v >= 0.3 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(0.3 - v, 0, 0.25),
    rule: "demo rule: limiting below 0.3 %, favourable from 0.6 %",
  },
  {
    name: "soil_depth",
    unit: "cm",
    category: "soil",
    evidence: "ml_predicted",
    digits: 0,
    importance: 0.14,
    reversibility: (v) => (v < 20 ? "irreversible" : "partially_reversible"),
    irreversible: true,
    sample: { favourable: (r) => uniform(r, 80, 150), marginal: (r) => uniform(r, 40, 80), limiting: (r) => uniform(r, 8, 40) },
    classify: (v) => (v >= 80 ? "favourable" : v >= 40 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(40 - v, 0, 32),
    rule: "demo rule: limiting below 40 cm, favourable from 80 cm",
  },
  {
    name: "slope",
    unit: "deg",
    category: "terrain",
    evidence: "observed",
    digits: 1,
    importance: 0.12,
    reversibility: () => "irreversible",
    irreversible: true,
    sample: { favourable: (r) => uniform(r, 0.3, 5), marginal: (r) => uniform(r, 5, 12), limiting: (r) => uniform(r, 12, 28) },
    classify: (v) => (v < 5 ? "favourable" : v < 12 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(v, 12, 28),
    rule: "demo rule: limiting from 12 deg, favourable below 5 deg",
  },
  {
    name: "sand_fraction",
    unit: "%",
    category: "soil",
    evidence: "ml_predicted",
    digits: 0,
    importance: 0.07,
    reversibility: () => "partially_reversible",
    irreversible: false,
    sample: { favourable: (r) => uniform(r, 25, 55), marginal: (r) => uniform(r, 55, 70), limiting: (r) => uniform(r, 70, 92) },
    classify: (v) => (v < 55 ? "favourable" : v < 70 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(v, 70, 92),
    rule: "demo rule: limiting from 70 % sand, favourable below 55 %",
  },
  {
    name: "water_availability",
    unit: "index 0-1",
    category: "water",
    evidence: "expert_rule",
    digits: 2,
    importance: 0.1,
    reversibility: () => "partially_reversible",
    irreversible: false,
    sample: { favourable: (r) => uniform(r, 0.6, 0.95), marginal: (r) => uniform(r, 0.3, 0.6), limiting: (r) => uniform(r, 0.04, 0.3) },
    classify: (v) => (v >= 0.6 ? "favourable" : v >= 0.3 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(0.3 - v, 0, 0.26),
    rule: "demo rule: limiting below 0.3, favourable from 0.6",
  },
  {
    name: "vegetation_ndvi",
    unit: "NDVI",
    category: "vegetation",
    evidence: "observed",
    digits: 2,
    importance: 0.05,
    reversibility: null,
    irreversible: false,
    sample: { favourable: (r) => uniform(r, 0.25, 0.55), marginal: (r) => uniform(r, 0.12, 0.25), limiting: (r) => uniform(r, 0.03, 0.12) },
    classify: (v) => (v >= 0.25 ? "favourable" : v >= 0.12 ? "marginal" : "limiting"),
    overshoot: (v) => lerpClamp(0.12 - v, 0, 0.09),
    rule: "demo rule: limiting below 0.12, favourable from 0.25",
  },
];

/** Probability that a factor draws "limiting" / "marginal" per class. */
const BAND_PROBS: Record<SuitabilityClassCode, { lim: number; marg: number }> = {
  1: { lim: 0, marg: 0.22 },
  2: { lim: 0.14, marg: 0.38 },
  3: { lim: 0.32, marg: 0.34 },
  4: { lim: 0.48, marg: 0.3 },
  5: { lim: 0.2, marg: 0.3 },
};

const REVERSIBLE_SET = ["soil_salinity_ec", "soil_organic_carbon", "soil_ph", "water_availability", "sand_fraction"];
const IRREVERSIBLE_SET = ["slope", "soil_depth", "rainfall"];

function drawBands(r: Rng, cls: SuitabilityClassCode): Record<string, Band> {
  const { lim, marg } = BAND_PROBS[cls];
  const bands: Record<string, Band> = {};
  for (const f of FACTORS) {
    const x = r();
    bands[f.name] = x < lim ? "limiting" : x < lim + marg ? "marginal" : "favourable";
  }
  const limiting = () => Object.keys(bands).filter((k) => bands[k] === "limiting" && k !== "vegetation_ndvi");
  const setLimiting = (pool: string[]) => {
    const candidates = pool.filter((k) => bands[k] !== "limiting");
    if (candidates.length > 0) bands[pick(r, candidates)] = "limiting";
  };

  if (cls === 1) {
    for (const k of Object.keys(bands)) if (bands[k] === "limiting") bands[k] = "marginal";
  } else if (cls === 2) {
    if (limiting().length === 0) setLimiting([...REVERSIBLE_SET, "slope"]);
    // class 2 keeps at most two limiting factors
    const l = limiting();
    for (const k of l.slice(2)) bands[k] = "marginal";
  } else if (cls === 3) {
    // reclamation: the limitations are addressable (reversible), at most one irreversible factor
    while (limiting().filter((k) => REVERSIBLE_SET.includes(k)).length < 2) {
      const before = limiting().length;
      setLimiting(REVERSIBLE_SET);
      if (limiting().length === before) break;
    }
    const irrev = limiting().filter((k) => IRREVERSIBLE_SET.includes(k));
    for (const k of irrev.slice(1)) bands[k] = "marginal";
  } else if (cls === 4) {
    if (limiting().filter((k) => IRREVERSIBLE_SET.includes(k)).length === 0) setLimiting(IRREVERSIBLE_SET);
    while (limiting().length < 3) {
      const before = limiting().length;
      setLimiting([...IRREVERSIBLE_SET, ...REVERSIBLE_SET]);
      if (limiting().length === before) break;
    }
  }
  return bands;
}

const STATUS_PHRASE: Record<Band, string> = {
  favourable: "within the favourable range",
  marginal: "in the marginal range",
  limiting: "in the limiting range",
};

const prettyName = (n: string): string => n.replace(/_/g, " ");

function fmt(v: number, digits: number): number {
  return round(v, digits);
}

/* ------------------------------------------------------------------ interventions (catalogue; placeholders, no citations) */

const NO_CITATION = "No source study attached: demonstration placeholder (Phase A)";

const INTERVENTIONS: Record<string, Omit<Intervention, "source_refs" | "evidence">> = {
  "iv-leaching-gypsum": {
    id: "iv-leaching-gypsum",
    name: "Leaching with gypsum amendment",
    description: "Apply a calcium amendment and leach soluble salts below the root zone with good-quality water, with drainage.",
    targets_factor: "soil_salinity_ec",
    expected_effect: "Lowers root-zone salinity. Direction only: magnitude is not quantified in demonstration data.",
  },
  "iv-salt-tolerant-crops": {
    id: "iv-salt-tolerant-crops",
    name: "Salt-tolerant crop selection",
    description: "Choose crops and cultivars tolerant of the remaining salinity while the soil is being reclaimed.",
    targets_factor: "soil_salinity_ec",
    expected_effect: "Allows production at moderate salinity. Direction only.",
  },
  "iv-organic-matter": {
    id: "iv-organic-matter",
    name: "Organic matter build-up",
    description: "Incorporate compost or crop residues and reduce tillage to raise soil organic carbon and water retention.",
    targets_factor: "soil_organic_carbon",
    expected_effect: "Raises soil organic carbon and water holding capacity over several seasons. Direction only.",
  },
  "iv-sulfur-ph": {
    id: "iv-sulfur-ph",
    name: "pH correction",
    description: "Apply an acidifying amendment (for example elemental sulfur) where the soil is strongly alkaline.",
    targets_factor: "soil_ph",
    expected_effect: "Moves pH toward the favourable range; slow in calcareous soils. Direction only.",
  },
  "iv-ripping": {
    id: "iv-ripping",
    name: "Deep ripping",
    description: "Break up compacted or cemented layers to deepen the effective rooting zone.",
    targets_factor: "soil_depth",
    expected_effect: "Increases effective rooting depth where a breakable layer exists. Cannot add soil where bedrock is shallow.",
  },
  "iv-terracing": {
    id: "iv-terracing",
    name: "Contour terracing and bunds",
    description: "Shape contour terraces or bunds to reduce slope length and runoff velocity.",
    targets_factor: "slope",
    expected_effect: "Reduces erosion and retains runoff on sloping land. Direction only.",
  },
  "iv-runoff-harvesting": {
    id: "iv-runoff-harvesting",
    name: "Runoff and rainwater harvesting",
    description: "Capture and store runoff with micro-catchments, ponds or cisterns to supplement scarce rainfall.",
    targets_factor: "rainfall",
    expected_effect: "Adds supplementary water for establishment and dry spells. Direction only.",
  },
  "iv-drip-irrigation": {
    id: "iv-drip-irrigation",
    name: "Drip irrigation",
    description: "Deliver water and nutrients to the root zone with a pressurised drip network and fertigation.",
    targets_factor: "water_availability",
    expected_effect: "Makes limited water usable by crops with low losses. Direction only.",
  },
  "iv-windbreak-mulch": {
    id: "iv-windbreak-mulch",
    name: "Windbreaks and mulching",
    description: "Plant windbreaks and mulch the surface to cut wind erosion and evaporation on light soils.",
    targets_factor: "sand_fraction",
    expected_effect: "Reduces wind erosion and surface evaporation. Direction only.",
  },
};

const FACTOR_TO_INTERVENTIONS: Record<string, string[]> = {
  soil_salinity_ec: ["iv-leaching-gypsum", "iv-salt-tolerant-crops"],
  soil_organic_carbon: ["iv-organic-matter"],
  soil_ph: ["iv-sulfur-ph"],
  soil_depth: ["iv-ripping"],
  slope: ["iv-terracing"],
  rainfall: ["iv-runoff-harvesting", "iv-drip-irrigation"],
  sand_fraction: ["iv-organic-matter", "iv-windbreak-mulch"],
  water_availability: ["iv-runoff-harvesting", "iv-drip-irrigation"],
};

const roundTo = (v: number, step: number): number => Math.round(v / step) * step;

/* ------------------------------------------------------------------ geometry helpers */

interface Site {
  lon: number;
  lat: number;
  cls: SuitabilityClassCode;
  q: number;
}

const AREA_MEDIAN_HA: Record<SuitabilityClassCode, number> = { 1: 90, 2: 170, 3: 380, 4: 900, 5: 1500 };

function buildRing(r: Rng, lon0: number, lat0: number, radiusKm: number, scale = 1): Position[] {
  const n = 18;
  const p1 = r() * 6.283;
  const p2 = r() * 6.283;
  const p3 = r() * 6.283;
  const elong = uniform(r, 1, 1.55);
  const rot = r() * Math.PI;
  const kx = kmPerDegLon(lat0);
  const pts: Position[] = [];
  for (let i = 0; i < n; i++) {
    const th = ((i + uniform(r, -0.18, 0.18)) / n) * 2 * Math.PI;
    const rr = radiusKm * scale * (1 + 0.26 * Math.sin(2 * th + p1) + 0.16 * Math.sin(3 * th + p2) + 0.09 * Math.sin(5 * th + p3));
    const x = rr * Math.cos(th) * elong;
    const y = (rr * Math.sin(th)) / elong;
    const xr = x * Math.cos(rot) - y * Math.sin(rot);
    const yr = x * Math.sin(rot) + y * Math.cos(rot);
    pts.push([round6(lon0 + xr / kx), round6(lat0 + yr / KM_PER_DEG_LAT)]);
  }
  pts.push(pts[0] as Position);
  return pts;
}

/* ------------------------------------------------------------------ main */

export function generateDemoDataset(opts: GenerateOptions): DemoDataset {
  const seed = opts.seed ?? 20251122;
  const count = opts.count ?? 240;
  const createdAt = opts.now ?? new Date().toISOString();
  const r = mulberry32(seed);
  const ring = opts.ring;
  const [w, s, e, n] = ringBBox(ring);

  const randomInside = (margin = 0): [number, number] => {
    for (let i = 0; i < 5000; i++) {
      const lon = uniform(r, w, e);
      const lat = uniform(r, s, n);
      if (!pointInRing(lon, lat, ring)) continue;
      if (margin > 0) {
        const dx = margin / kmPerDegLon(lat);
        const dy = margin / KM_PER_DEG_LAT;
        const ok = [
          [lon + dx, lat],
          [lon - dx, lat],
          [lon, lat + dy],
          [lon, lat - dy],
        ].every(([x, y]) => pointInRing(x as number, y as number, ring));
        if (!ok) continue;
      }
      return [lon, lat];
    }
    return [(w + e) / 2, (s + n) / 2];
  };

  const kmDist = (a: [number, number], b: [number, number]): number => {
    const dx = (a[0] - b[0]) * kmPerDegLon((a[1] + b[1]) / 2);
    const dy = (a[1] - b[1]) * KM_PER_DEG_LAT;
    return Math.hypot(dx, dy);
  };

  // latent "synthetic potential" field: a few broad bumps (arbitrary places, not real agricultural areas)
  const hotspots = Array.from({ length: 6 }, () => ({ at: randomInside(8), sigma: uniform(r, 22, 55), w: uniform(r, 0.6, 1) }));
  const zones = Array.from({ length: 3 }, () => ({ at: randomInside(18), radius: uniform(r, 14, 30) }));
  const potential = (p: [number, number]): number =>
    hotspots.reduce((a, h) => a + h.w * Math.exp(-(kmDist(p, h.at) ** 2) / (2 * h.sigma ** 2)), 0) + normal(r, 0, 0.1);

  // candidate sites -> class by quantile of potential (class 5 from the synthetic restriction zones)
  const sites: Site[] = [];
  const raw = Array.from({ length: Math.round(count * 1.5) }, () => {
    const p = randomInside(6);
    return { p, v: potential(p), inZone: zones.some((z) => kmDist(p, z.at) < z.radius) };
  });
  const zoneSites = raw.filter((x) => x.inZone).slice(0, Math.max(4, Math.round(count * 0.09)));
  const rest = raw.filter((x) => !zoneSites.includes(x)).slice(0, count - zoneSites.length);
  rest.sort((a, b) => b.v - a.v);
  const nRest = rest.length;
  const cuts: [SuitabilityClassCode, number][] = [
    [1, 0.15],
    [2, 0.39],
    [3, 0.68],
    [4, 1],
  ];
  rest.forEach((x, i) => {
    const frac = (i + 1) / nRest;
    const cls = (cuts.find(([, c]) => frac <= c) ?? [4, 1])[0];
    sites.push({ lon: x.p[0], lat: x.p[1], cls, q: x.v });
  });
  for (const z of zoneSites) sites.push({ lon: z.p[0], lat: z.p[1], cls: 5, q: z.v });

  // place polygons without overlap, big first
  const placed: { at: [number, number]; rKm: number }[] = [];
  const order = shuffle(r, sites).sort((a, b) => AREA_MEDIAN_HA[b.cls] - AREA_MEDIAN_HA[a.cls]);
  const units: { ring: Position[]; site: Site; center: [number, number] }[] = [];

  for (const site of order) {
    let targetHa = clamp(AREA_MEDIAN_HA[site.cls] * Math.exp(normal(r, 0, 0.7)), 8, 8000);
    const candSeed = Math.floor(r() * 2 ** 31);
    let success: Position[] | null = null;
    let center: [number, number] = [site.lon, site.lat];
    for (let attempt = 0; attempt < 70 && !success; attempt++) {
      // first try the site itself, then jitter around it; shrink the target every 12 failed attempts
      const jitterKm = attempt < 20 ? 0 : Math.min(10, 1 + attempt * 0.18);
      const lon = site.lon + (jitterKm ? normal(r, 0, jitterKm) / kmPerDegLon(site.lat) : 0);
      const lat = site.lat + (jitterKm ? normal(r, 0, jitterKm) / KM_PER_DEG_LAT : 0);
      if (attempt > 0 && attempt % 12 === 0) targetHa = Math.max(8, targetHa * 0.64);
      if (!pointInRing(lon, lat, ring)) continue;
      // fit the polygon area to the target in the equal-area projection (area scales with radius^2)
      const baseRadiusKm = Math.sqrt((targetHa * 0.01) / Math.PI); // ha -> km2 -> radius
      let scale = 1;
      let cand = buildRing(mulberry32(candSeed), lon, lat, baseRadiusKm, scale);
      for (let pass = 0; pass < 3; pass++) {
        const haNow = m2ToHa(polygonAreaM2([cand]));
        scale *= Math.sqrt(targetHa / Math.max(haNow, 1e-6));
        cand = buildRing(mulberry32(candSeed), lon, lat, baseRadiusKm, scale);
      }
      const extentKm = Math.max(...cand.map(([x, y]) => kmDist([lon, lat], [x as number, y as number])));
      if (placed.some((p) => kmDist([lon, lat], p.at) < (extentKm + p.rKm) * 0.92)) continue;
      if (!cand.every(([x, y]) => pointInRing(x as number, y as number, ring))) continue;
      placed.push({ at: [lon, lat], rKm: extentKm });
      center = [lon, lat];
      success = cand;
    }
    if (success) units.push({ ring: success, site, center });
  }

  // stable ordering: west-to-east, then south-to-north, so ids are deterministic and spatially coherent
  units.sort((a, b) => (a.center[0] === b.center[0] ? a.center[1] - b.center[1] : a.center[0] - b.center[0]));

  const suitFeatures: SuitabilityFeature[] = [];
  const restFeatures: RestorationFeature[] = [];
  let m2Counter = 0;

  units.forEach((u, idx) => {
    const id = `m1-${opts.regionId}-${idx + 1}`;
    const cls = u.site.cls;
    const bands = drawBands(r, cls);
    const values: Record<string, number> = {};
    for (const f of FACTORS) {
      // sample inside the intended band, round for display, and re-draw if rounding crossed a threshold
      const band = bands[f.name] as Band;
      let v = fmt(f.sample[band](r), f.digits);
      for (let i = 0; i < 12 && f.classify(v) !== band; i++) v = fmt(f.sample[band](r), f.digits);
      values[f.name] = v;
    }

    const factors: SuitabilityFactor[] = FACTORS.map((f) => {
      const v = fmt(values[f.name] as number, f.digits);
      const band = f.classify(v);
      return {
        name: f.name,
        value: v,
        unit: f.unit,
        status: band as FactorStatus,
        evidence: f.evidence,
        note: `Synthetic value ${v}${f.unit ? " " + f.unit : ""}, ${STATUS_PHRASE[band]} (${f.rule}).`,
        importance: round(f.importance * uniform(r, 0.8, 1.2), 3),
        category: f.category,
      };
    });
    if (cls === 5) {
      factors.push({
        name: "land_use_restriction",
        value: "Restricted zone (synthetic)",
        status: "restricted",
        evidence: "expert_rule",
        note: "Synthetic restriction zone for demonstration. No real protected-area or land-tenure data was used.",
        importance: 0.4,
        category: "restriction",
      });
    }

    // class probabilities (synthetic) -> confidence = top probability
    const topMean: Record<SuitabilityClassCode, number> = { 1: 0.8, 2: 0.66, 3: 0.64, 4: 0.78, 5: 0.86 };
    const top = clamp(normal(r, topMean[cls], 0.09), 0.42, 0.97);
    const weights: Record<string, number> = {};
    for (const k of ["1", "2", "3", "4", "5"] as ClassKey[]) {
      const d = Math.abs(Number(k) - cls);
      weights[k] = d === 1 ? 0.5 : d === 2 ? 0.2 : 0.08;
    }
    if (cls === 5) {
      for (const k of ["1", "2", "3", "4"]) weights[k] = 0.25;
    }
    weights[String(cls)] = 0;
    const wsum = Object.values(weights).reduce((a, b) => a + b, 0);
    const probs = {} as Record<ClassKey, number>;
    let acc = 0;
    for (const k of ["1", "2", "3", "4", "5"] as ClassKey[]) {
      if (Number(k) === cls) continue;
      probs[k] = round(((1 - top) * (weights[k] as number)) / wsum, 3);
      acc += probs[k];
    }
    probs[String(cls) as ClassKey] = round(1 - acc, 3);
    const confidence = probs[String(cls) as ClassKey];

    const area_m2 = polygonAreaM2([u.ring]);
    const area_ha = roundArea(m2ToHa(area_m2));
    const area_dunum = roundArea(m2ToDunum(area_m2));
    const centroid: [number, number] = [round6(u.center[0]), round6(u.center[1])];
    const meta = SUITABILITY_CLASSES[cls];

    suitFeatures.push({
      type: "Feature",
      id,
      geometry: { type: "Polygon", coordinates: [u.ring] },
      properties: {
        id,
        class_code: cls,
        class_label: meta.label,
        area_ha,
        area_dunum,
        confidence,
        confidence_method: DEMO_CONFIDENCE_METHOD,
        class_probabilities: probs,
        factors,
        centroid,
        effective_resolution_m: 30,
        provenance: {
          model_version: DEMO_MODEL_VERSION,
          label_basis: "none: synthetic demonstration (no labels, no training)",
          data_sources: [DEMO_SOURCE_LABEL],
        },
      },
    });

    if (cls !== 3 && cls !== 4) return;

    /* ------------------------------ Model 2 (synthetic) */
    const limiting: LimitingFactor[] = [];
    for (const f of FACTORS) {
      if (!f.reversibility) continue;
      const fac = factors.find((x) => x.name === f.name);
      if (!fac || fac.status !== "limiting") continue;
      const v = fac.value as number;
      const rev = f.reversibility(v);
      const sev = round(clamp(0.3 + 0.65 * f.overshoot(v) + normal(r, 0, 0.03), 0.25, 0.97), 2);
      limiting.push({
        factor: f.name,
        severity: sev,
        reversibility: rev,
        evidence: "expert_rule",
        detail: `Synthetic ${prettyName(f.name)} of ${v}${f.unit ? " " + f.unit : ""} is in the limiting range (${f.rule}). Reversibility is an expert-rule assignment, not an observed outcome.`,
      });
    }
    const maxOf = (rev: Reversibility): number => Math.max(0, ...limiting.filter((l) => l.reversibility === rev).map((l) => l.severity));
    const maxIrrev = maxOf("irreversible");
    const maxPartial = maxOf("partially_reversible");
    const maxRev = maxOf("reversible");
    const score = round(clamp(0.92 - 0.47 * maxIrrev - 0.3 * maxPartial - 0.2 * maxRev + normal(r, 0, 0.03), 0.02, 0.95), 2);
    const fclass: FeasibilityClass = score >= 0.58 ? "high" : score >= 0.38 ? "moderate" : score >= 0.2 ? "low" : "not_feasible";
    const fconf = round(clamp(normal(r, 0.6, 0.1), 0.35, 0.88), 2);
    const half = round((1 - fconf) * 0.45, 2);
    const feasibility: Feasibility = {
      score,
      class: fclass,
      confidence: fconf,
      interval: [round(clamp(score - half, 0, 1), 2), round(clamp(score + half, 0, 1), 2)],
    };

    const ivIds = new Set<string>();
    for (const l of limiting) for (const iv of FACTOR_TO_INTERVENTIONS[l.factor] ?? []) ivIds.add(iv);
    if (ivIds.size === 0) ivIds.add("iv-organic-matter");
    const interventions: Intervention[] = [...ivIds].map((k) => ({
      ...(INTERVENTIONS[k] as (typeof INTERVENTIONS)[string]),
      evidence: "expert_rule" as const,
      source_refs: [NO_CITATION],
    }));

    const rainfall = values["rainfall"] as number;
    const saline = limiting.some((l) => l.factor === "soil_salinity_ec");
    const baseWater = 2500 + Math.max(0, 160 - rainfall) * 22 + (saline ? 1800 : 0);
    const lowInput = ["iv-organic-matter", "iv-windbreak-mulch", "iv-runoff-harvesting", "iv-terracing", "iv-sulfur-ph"].filter((k) => ivIds.has(k));
    const minPost: SuitabilityClassCode = maxIrrev >= 0.6 ? 3 : maxIrrev >= 0.35 ? 2 : 1;
    const postFor = (steps: number): SuitabilityClassCode => Math.max(minPost, (cls as number) - steps) as SuitabilityClassCode;

    const scenarios: RestorationScenario[] = [];
    if (fclass !== "not_feasible") {
      const mk = (
        key: string,
        name: string,
        ids: string[],
        steps: number,
        mult: number,
        sources: string[],
        infra: string[],
        crops: string[],
        years: [number, number],
        risks: string[],
      ): void => {
        const central = roundTo(baseWater * mult * uniform(r, 0.92, 1.08), 50);
        const post = postFor(steps);
        scenarios.push({
          id: `${id}-${key}`,
          name,
          intervention_ids: ids.length ? ids : ["iv-organic-matter"],
          post_class_code: post,
          post_class_probability: round(clamp(0.3 + 0.55 * score - 0.05 * (steps - 1) + normal(r, 0, 0.04), 0.12, 0.88), 2),
          water_requirement_m3_ha_yr: { low: roundTo(central * 0.78, 50), central, high: roundTo(central * 1.32, 50) },
          water_sources: sources,
          infrastructure: infra,
          crop_categories: crops,
          time_to_effect_years: { low: years[0], high: years[1] },
          residual_risks: [...risks, "No field validation exists for this synthetic scenario outcome"],
          evidence: "simulated",
        });
      };
      mk(
        "conservative",
        "Conservative: low-input soil and water conservation",
        lowInput,
        1,
        0.55,
        ["Rainwater harvesting", "Existing groundwater wells"],
        ["Contour bunds or micro-catchments", "Mulching"],
        ["Drought-tolerant tree crops", "Forage and range shrubs"],
        [4, 8],
        ["Slow organic carbon build-up in hot, dry soils", "Erosion during establishment"],
      );
      mk(
        "standard",
        "Standard: drip irrigation with soil amendment",
        [...ivIds].filter((k) => k !== "iv-salt-tolerant-crops"),
        maxIrrev < 0.7 ? 2 : 1,
        1,
        ["Treated wastewater", "Groundwater", "Rainwater harvesting"],
        ["Drip network", "On-farm storage pond", "Pumping"],
        ["Tree crops (olive or fig type)", "Forage crops", "Winter cereals with supplementary irrigation"],
        [3, 6],
        ["Dependence on a limited water source", "Salt re-accumulation without drainage"],
      );
      mk(
        "intensive",
        "Intensive: full infrastructure and soil rebuild",
        [...ivIds, "iv-drip-irrigation"].filter((k, i, a) => a.indexOf(k) === i),
        maxIrrev < 0.5 ? 3 : 2,
        1.35,
        ["Desalinated brackish water", "Treated wastewater", "Groundwater"],
        ["Drip network", "Subsurface drainage", "Storage and treatment unit", "Power supply"],
        ["Salt-tolerant tree crops (date-palm type)", "Vegetables under protection", "Forage crops"],
        [2, 5],
        ["Energy and maintenance cost of the infrastructure", "Groundwater depletion", "Salt re-accumulation without drainage"],
      );
    }

    const mv = (value: number, unit: string, unc: number, evidence: Evidence = "ml_predicted"): MeasuredValue => ({
      value,
      unit,
      evidence,
      uncertainty: round(unc, 2),
    });
    const sand = values["sand_fraction"] as number;
    const clay = round(clamp(uniform(r, 6, 28), 4, 100 - sand - 2), 0);
    const silt = round(100 - sand - clay, 0);
    const elevation = round(uniform(r, 520, 1650), 0);
    const slopeV = values["slope"] as number;
    const erosion = slopeV >= 12 || rainfall < 60 ? "high" : slopeV >= 5 ? "moderate" : "low";
    m2Counter += 1;
    const m2id = `m2-${opts.regionId}-${m2Counter}`;
    restFeatures.push({
      type: "Feature",
      id: m2id,
      geometry: { type: "Polygon", coordinates: [u.ring] },
      properties: {
        id: m2id,
        source_polygon_id: id,
        current_class_code: cls,
        area_ha,
        area_dunum,
        limiting_factors: limiting,
        feasibility,
        interventions,
        scenarios,
        soil: {
          ph: mv(fmt(values["soil_ph"] as number, 1), "", 0.3),
          ec_ds_m: mv(fmt(values["soil_salinity_ec"] as number, 1), "dS/m", 0.2 * (values["soil_salinity_ec"] as number) + 0.3),
          soc_pct: mv(fmt(values["soil_organic_carbon"] as number, 2), "%", 0.12),
          sand_pct: mv(fmt(sand, 0), "%", 6),
          silt_pct: mv(silt, "%", 5),
          clay_pct: mv(clay, "%", 4),
          depth_cm: mv(fmt(values["soil_depth"] as number, 0), "cm", 12),
        },
        terrain: {
          elevation_m: mv(elevation, "m", 15, "observed"),
          slope_deg: mv(fmt(slopeV, 1), "deg", 0.6, "observed"),
          erosion_risk: { value: erosion, evidence: "expert_rule" },
        },
        climate: {
          rainfall_mm_yr: mv(fmt(rainfall, 0), "mm/yr", 18, "observed"),
          temp_mean_c: mv(fmt(26 - elevation * 0.0085 + normal(r, 0, 0.6), 1), "°C", 0.8, "observed"),
        },
        provenance: {
          model_version: DEMO_MODEL_VERSION,
          evidence_summary:
            "All values are synthetic demonstration data. Scenario outcomes are simulated by design; none is an observed restoration result.",
          data_sources: [DEMO_SOURCE_LABEL],
          source_studies: [],
        },
      },
    });
  });

  return {
    regionId: opts.regionId,
    seed,
    createdAt,
    suitability: { type: "FeatureCollection", features: suitFeatures },
    restoration: { type: "FeatureCollection", features: restFeatures },
  };
}
