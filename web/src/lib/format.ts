const EN = "en-US";

export const fmtNum = (n: number, maxDigits = 1, minDigits = 0): string =>
  n.toLocaleString(EN, { minimumFractionDigits: minDigits, maximumFractionDigits: maxDigits });

export const fmtInt = (n: number): string => n.toLocaleString(EN, { maximumFractionDigits: 0 });

/** Hectares: 2 decimals below 100, 1 below 10,000, else integer. */
export function fmtHa(ha: number): string {
  if (Math.abs(ha) < 100) return fmtNum(ha, 2);
  if (Math.abs(ha) < 10_000) return fmtNum(ha, 1);
  return fmtInt(ha);
}

export const fmtDunum = fmtHa;

export const fmtPct = (frac: number, digits = 1): string => `${(frac * 100).toLocaleString(EN, { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;

export const fmtConfidence = (c: number): string => c.toFixed(2);

export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(EN, { dateStyle: "medium", timeStyle: "short" });
}

/** "1,200 – 3,400" */
export const fmtRange = (lo: number, hi: number, digits = 0): string => `${fmtNum(lo, digits)}–${fmtNum(hi, digits)}`;
