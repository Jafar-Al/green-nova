import { CLASS_LIST } from "@/lib/classes";
import { fmtDunum, fmtHa, fmtInt, fmtPct } from "@/lib/format";
import { DUNUM_DEFINITION } from "@/lib/units";
import type { SuitabilityRun } from "@/lib/types";
import { ClassSwatch } from "@/components/ui/primitives";

/** Per-class area table. Both units always shown; the dunum definition is printed with it. */
export function AreaStats({ run, activeClasses }: { run: SuitabilityRun; activeClasses?: Set<number> }) {
  return (
    <div>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Land area by class (scrollable table)">
        <table className="data-table">
          <caption className="visually-hidden">Land area by suitability class, in hectares and dunums</caption>
          <thead>
            <tr>
              <th scope="col">Class</th>
              <th scope="col" className="num">
                Units
              </th>
              <th scope="col" className="num">
                Hectares
              </th>
              <th scope="col" className="num">
                Dunums
              </th>
            </tr>
          </thead>
          <tbody>
            {CLASS_LIST.map((c) => {
              const s = run.stats.find((x) => x.code === c.code);
              const dim = activeClasses && !activeClasses.has(c.code);
              return (
                <tr key={c.code} className={dim ? "opacity-45" : undefined}>
                  <th scope="row" className="!border-b !border-line !px-3 !py-2 !text-sm !normal-case !tracking-normal !text-ink">
                    <span className="flex items-center gap-2">
                      <ClassSwatch code={c.code} size="sm" />
                      <span className="font-medium">{c.short}</span>
                    </span>
                    <span className="mt-1.5 flex items-center gap-2">
                      <span aria-hidden="true" className="block h-1 flex-1 overflow-hidden rounded-xs bg-[color-mix(in_oklab,var(--ink)_12%,transparent)]">
                        <span className="block h-full" style={{ inlineSize: `${(s?.share ?? 0) * 100}%`, background: c.color }} />
                      </span>
                      <span className="w-12 text-end text-xs font-normal text-ink-3 tnum">{fmtPct(s?.share ?? 0)}</span>
                    </span>
                  </th>
                  <td className="num">{fmtInt(s?.polygon_count ?? 0)}</td>
                  <td className="num">{fmtHa(s?.area_ha ?? 0)}</td>
                  <td className="num">{fmtDunum(s?.area_dunum ?? 0)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" className="!px-3 !py-2 !text-sm !normal-case !tracking-normal !text-ink">
                All units
              </th>
              <td className="num font-semibold">{fmtInt(run.polygon_count)}</td>
              <td className="num font-semibold">{fmtHa(run.total_area_ha)}</td>
              <td className="num font-semibold">{fmtDunum(run.total_area_dunum)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink-3">
        {DUNUM_DEFINITION}. Shares are of the area covered by the analysed land units, not of the whole governorate.
      </p>
    </div>
  );
}
