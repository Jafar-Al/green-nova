/**
 * Area units. Jordanian metric dunum: 1 dunum = 1,000 m2 = 0.1 ha  (so 1 ha = 10 dunum = 10,000 m2).
 * This definition must be stated wherever areas are shown (UI + exports).
 */
export const M2_PER_DUNUM = 1000;
export const M2_PER_HA = 10_000;
export const DUNUM_PER_HA = M2_PER_HA / M2_PER_DUNUM; // 10

export const DUNUM_DEFINITION = "1 dunum = 1,000 m² = 0.1 ha";

export const haToDunum = (ha: number): number => ha * DUNUM_PER_HA;
export const dunumToHa = (dunum: number): number => dunum / DUNUM_PER_HA;
export const m2ToHa = (m2: number): number => m2 / M2_PER_HA;
export const m2ToDunum = (m2: number): number => m2 / M2_PER_DUNUM;

/** Rounds like the contract examples: keep 2 decimals for values < 100, else 1 decimal, else integer for large. */
export function roundArea(v: number): number {
  if (!Number.isFinite(v)) return 0;
  if (Math.abs(v) < 100) return Math.round(v * 100) / 100;
  if (Math.abs(v) < 10_000) return Math.round(v * 10) / 10;
  return Math.round(v);
}
