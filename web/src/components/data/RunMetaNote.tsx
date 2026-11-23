import type { SuitabilityRun } from "@/lib/types";
import { Disclosure } from "@/components/ui/primitives";

const asText = (v: unknown): string | null => (typeof v === "string" && v.length > 0 ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/**
 * Run-level honesty block for REAL Model 1 results: grid vs effective resolution, what confidence means, how labels were made.
 * Reads run_metadata fields when present; renders nothing for runs without them.
 */
export function RunMetaNote({ run }: { run: SuitabilityRun }) {
  const m = run.metadata as Record<string, unknown>;
  const grid = num(m.grid_resolution_m);
  const eff = num(m.effective_resolution_m);
  const conf = asText(m.confidence_method);
  const note = asText(m.effective_resolution_note);
  const basis = m.label_basis;
  if (grid === null && eff === null && !conf) return null;
  return (
    <div className="grid gap-2 rounded-sm border border-line p-3 text-xs text-ink-2">
      {eff !== null ? (
        <p className="m-0">
          <strong className="text-ink">Effective resolution {eff.toLocaleString("en-US")} m.</strong>
          {grid !== null ? ` The analysis grid is ${grid.toLocaleString("en-US")} m, but` : " "} the class of a unit is driven by inputs coarser than the grid, so no unit is more precise than the effective resolution.
          {note ? ` ${note}` : ""}
        </p>
      ) : null}
      {conf ? (
        <p className="m-0">
          <strong className="text-ink">Confidence is not accuracy.</strong> {conf}
        </p>
      ) : null}
      {basis ? (
        <Disclosure summary="How the classes were labelled" className="rounded-sm border border-line px-3">
          {typeof basis === "string" ? (
            <p className="m-0 text-xs text-ink-2">{basis}</p>
          ) : (
            <ul className="m-0 list-none p-0 text-xs text-ink-2">
              {Object.entries(basis as Record<string, string>).map(([k, v]) => (
                <li key={k} className="py-1">
                  <strong className="text-ink">Class {k}:</strong> {String(v)}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1 text-xs text-ink-3">Labels are rule-derived and observed evidence; they have not been verified in the field.</p>
        </Disclosure>
      ) : null}
      <p className="m-0 text-ink-3">Model {String(m.model_version ?? "version not stated")}.</p>
    </div>
  );
}
