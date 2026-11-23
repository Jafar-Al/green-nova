/** Every view and every exported file that carries demo data must show this exact marker. */
export const DEMO_NOTICE = "DEMONSTRATION DATA — not a model prediction";

export const DEMO_DETAIL =
  "Synthetic, Ma’an-shaped records generated locally in your browser. No model produced them, and nothing here was measured on the ground. Polygon positions are arbitrary and are not derived from the satellite imagery beneath them.";

export const DEMO_MODEL_VERSION = "demo-synthetic-0";
export const DEMO_SOURCE_LABEL = "Synthetic generator (web/src/lib/demo, seeded, runs locally)";
export const DEMO_CONFIDENCE_METHOD =
  "Synthetic demonstration value: equals the top class probability of a synthetic draw. No model produced it and it is not a calibrated probability.";
