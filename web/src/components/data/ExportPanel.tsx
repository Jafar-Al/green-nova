"use client";

import { useState } from "react";
import { downloadText } from "@/lib/hooks";
import type { ExportArtifact, ExportFormat, ProviderCapabilities } from "@/lib/types";
import { IS_DEMO_MODE } from "@/lib/config";
import { Button } from "@/components/ui/primitives";
import { IconCheck, IconDownload } from "@/components/ui/icons";
import { ErrorState } from "@/components/ui/states";

export interface ExportItem {
  format: ExportFormat;
  label: string;
  description: string;
}

type Status = { state: "idle" } | { state: "working" } | { state: "done"; filename: string } | { state: "error"; message: string };

/** Export controls. Unavailable formats stay visible with the reason, never silently hidden. */
export function ExportPanel({
  title = "Export",
  items,
  capabilities,
  run,
  disabledReason,
  idPrefix,
}: {
  title?: string;
  items: ExportItem[];
  capabilities: ProviderCapabilities;
  run: (format: ExportFormat) => Promise<ExportArtifact>;
  disabledReason?: string | null;
  idPrefix: string;
}) {
  const [status, setStatus] = useState<Record<string, Status>>({});
  const doExport = async (format: ExportFormat) => {
    setStatus((s) => ({ ...s, [format]: { state: "working" } }));
    try {
      const art = await run(format);
      if (art.content !== undefined) downloadText(art.filename, art.mime, art.content);
      else if (art.url) window.open(art.url, "_blank", "noopener,noreferrer");
      setStatus((s) => ({ ...s, [format]: { state: "done", filename: art.filename } }));
    } catch (e) {
      setStatus((s) => ({ ...s, [format]: { state: "error", message: e instanceof Error ? e.message : "Export failed." } }));
    }
  };
  return (
    <section aria-labelledby={`${idPrefix}-title`} className="grid gap-3">
      <h3 id={`${idPrefix}-title`} className="h-panel">
        {title}
      </h3>
      {IS_DEMO_MODE ? <p className="m-0 text-xs text-ink-3">Exported demonstration files carry the DEMONSTRATION DATA marker inside the file.</p> : null}
      {disabledReason ? <p className="m-0 text-xs text-ink-3">{disabledReason}</p> : null}
      <ul className="m-0 grid list-none gap-2 p-0">
        {items.map((it) => {
          const cap = capabilities.exports[it.format];
          const st = status[it.format] ?? { state: "idle" };
          const blocked = !cap.available || !!disabledReason;
          const descId = `${idPrefix}-${it.format}-d`;
          return (
            <li key={it.format} className="grid gap-1 border-b border-line pb-2 last:border-b-0">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="m-0 text-sm font-semibold text-ink">{it.label}</p>
                  <p id={descId} className="m-0 text-xs text-ink-3">
                    {cap.available ? it.description : (cap.reason ?? "Not available.")}
                  </p>
                </div>
                <Button size="sm" onClick={() => void doExport(it.format)} disabled={blocked || st.state === "working"} aria-describedby={descId} aria-label={`Download ${it.label}`}>
                  {st.state === "done" ? <IconCheck className="size-4" /> : <IconDownload className="size-4" />}
                  {st.state === "working" ? "Preparing…" : st.state === "done" ? "Again" : "Download"}
                </Button>
              </div>
              {st.state === "done" ? (
                <p role="status" className="m-0 text-xs text-ok">
                  Saved {st.filename}
                </p>
              ) : null}
              {st.state === "error" ? <ErrorState title="Export failed" message={st.message} className="!p-3" /> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
