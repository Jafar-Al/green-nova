"use client";

import { IS_DEMO_MODE } from "@/lib/config";
import type { RegionList } from "@/lib/region-data";
import { FieldLabel } from "@/components/ui/primitives";

/** Country (Jordan) and governorate (Ma'an default) selectors. Unanalysed governorates stay selectable so the empty state is reachable. */
export function RegionSelectors({
  list,
  regionId,
  onRegion,
  idPrefix,
  loading,
}: {
  list: RegionList | null;
  regionId: string;
  onRegion: (id: string) => void;
  idPrefix: string;
  loading?: boolean;
}) {
  const countries = list?.countries ?? [{ code: "JO", name: "Jordan", available: true }];
  const regions = list?.regions ?? [];
  return (
    <div className="grid gap-3">
      <div>
        <FieldLabel htmlFor={`${idPrefix}-country`} hint="Jordan is the first configured country; more are added by configuration.">
          Country
        </FieldLabel>
        <select id={`${idPrefix}-country`} className="field" value="JO" onChange={() => undefined} disabled={countries.length <= 1} aria-describedby={`${idPrefix}-country-note`}>
          {countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </select>
        <span id={`${idPrefix}-country-note`} className="visually-hidden">
          Only Jordan is available in this release.
        </span>
      </div>
      <div>
        <FieldLabel htmlFor={`${idPrefix}-region`} hint={IS_DEMO_MODE ? "Governorate (ADM1). Ma’an is the demonstration region." : "Governorate (ADM1). All 12 governorates of Jordan are analysed."}>
          Governorate
        </FieldLabel>
        <select id={`${idPrefix}-region`} className="field" value={regionId} onChange={(e) => onRegion(e.target.value)} disabled={loading && regions.length === 0}>
          {regions.length === 0 ? <option value={regionId}>{loading ? "Loading…" : regionId}</option> : null}
          {regions.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name.replace("'", "’")}
              {r.available ? "" : " – no analysis in this release"}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
