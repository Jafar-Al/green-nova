/** Small seeded PRNG (mulberry32) so demo data is deterministic and testable. */
export type Rng = () => number;

export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const uniform = (r: Rng, lo: number, hi: number): number => lo + (hi - lo) * r();

/** Box-Muller. */
export function normal(r: Rng, mean = 0, sd = 1): number {
  const u = Math.max(r(), 1e-12);
  const v = r();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

export function pick<T>(r: Rng, arr: readonly T[]): T {
  return arr[Math.floor(r() * arr.length)] as T;
}

export function shuffle<T>(r: Rng, arr: readonly T[]): T[] {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [a[i], a[j]] = [a[j] as T, a[i] as T];
  }
  return a;
}

export const round = (v: number, digits = 0): number => {
  const f = 10 ** digits;
  return Math.round(v * f) / f;
};
