import { describe, expect, it } from "vitest";
import {
  formatLatLon,
  formatLatLonDms,
  geometryAreaHaDunum,
  geometryBBox,
  pointInPolygon,
  pointInRing,
  ringAreaM2,
} from "../geo";
import { DUNUM_DEFINITION, DUNUM_PER_HA, dunumToHa, haToDunum, m2ToDunum, m2ToHa, roundArea } from "../units";

describe("units", () => {
  it("1 dunum = 1,000 m2 = 0.1 ha", () => {
    expect(m2ToDunum(1000)).toBe(1);
    expect(m2ToHa(1000)).toBeCloseTo(0.1, 12);
    expect(haToDunum(1)).toBe(10);
    expect(dunumToHa(10)).toBe(1);
    expect(DUNUM_PER_HA).toBe(10);
    expect(DUNUM_DEFINITION).toContain("1,000");
  });
  it("roundArea keeps sensible precision", () => {
    expect(roundArea(12.3456)).toBe(12.35);
    expect(roundArea(123.456)).toBe(123.5);
    expect(roundArea(123456.7)).toBe(123457);
    expect(roundArea(Number.NaN)).toBe(0);
  });
});

describe("equal-area geometry", () => {
  // 0.01 deg x 0.01 deg at 30 N: 110.85 km/deg lat * 96.4 km/deg lon (WGS84) => ~1.0686 km2 = ~106.9 ha
  const sq = (lon: number, lat: number, d: number) => [
    [lon, lat],
    [lon + d, lat],
    [lon + d, lat + d],
    [lon, lat + d],
    [lon, lat],
  ];
  it("computes area in an equal-area projection, not in degrees", () => {
    const m2 = ringAreaM2(sq(36, 30, 0.01));
    expect(m2 / 1e6).toBeGreaterThan(1.06);
    expect(m2 / 1e6).toBeLessThan(1.078);
  });
  it("shrinks with latitude for the same degree box", () => {
    expect(ringAreaM2(sq(36, 60, 0.01))).toBeLessThan(ringAreaM2(sq(36, 30, 0.01)));
  });
  it("1 degree box at the equator matches the WGS84 value (~12,308 km2)", () => {
    const km2 = ringAreaM2(sq(0, 0, 1)) / 1e6;
    expect(km2).toBeGreaterThan(12290);
    expect(km2).toBeLessThan(12330);
  });
  it("returns ha and dunum consistently", () => {
    const { area_ha, area_dunum } = geometryAreaHaDunum({ type: "Polygon", coordinates: [sq(36, 30, 0.01)] });
    expect(area_dunum / area_ha).toBeCloseTo(10, 9);
  });
  it("subtracts holes", () => {
    const outer = sq(36, 30, 0.02);
    const hole = sq(36.005, 30.005, 0.01);
    const full = geometryAreaHaDunum({ type: "Polygon", coordinates: [outer] }).area_ha;
    const holed = geometryAreaHaDunum({ type: "Polygon", coordinates: [outer, hole] }).area_ha;
    expect(holed).toBeLessThan(full);
    expect(holed).toBeCloseTo(full * 0.75, 0);
  });
  it("point in ring / polygon and bbox", () => {
    const ring = sq(36, 30, 1);
    expect(pointInRing(36.5, 30.5, ring)).toBe(true);
    expect(pointInRing(37.5, 30.5, ring)).toBe(false);
    const hole = sq(36.4, 30.4, 0.2);
    expect(pointInPolygon(36.5, 30.5, [ring, hole])).toBe(false);
    expect(pointInPolygon(36.1, 30.1, [ring, hole])).toBe(true);
    expect(geometryBBox({ type: "Polygon", coordinates: [ring] })).toEqual([36, 30, 37, 31]);
  });
  it("formats coordinates", () => {
    expect(formatLatLon(36.12345, 30.54321)).toContain("30.54321");
    expect(formatLatLon(36.12345, 30.54321)).toContain("N");
    expect(formatLatLon(-1, -2)).toContain("S");
    expect(formatLatLonDms(36.5, 30.25)).toMatch(/30°15/);
  });
});
