import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import type { Evidence, FactorStatus, SuitabilityClassCode } from "@/lib/contract";
import { EVIDENCE_META, FACTOR_STATUS_META, SUITABILITY_CLASSES } from "@/lib/classes";
import { GlyphML, GlyphObserved, GlyphRule, GlyphSimulated, IconChevronDown } from "./icons";

const cx = (...a: Array<string | false | null | undefined>): string => a.filter(Boolean).join(" ");
export { cx };

/* ------------------------------------------------------------------ buttons */

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";
const variantClass: Record<Variant, string> = { primary: "btn-primary", secondary: "btn-secondary", ghost: "btn-ghost" };
const sizeClass: Record<Size, string> = { sm: "btn-sm", md: "", lg: "btn-lg" };

export function Button({
  variant = "secondary",
  size = "md",
  className,
  type = "button",
  ...p
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return <button type={type} className={cx("btn", variantClass[variant], sizeClass[size], className)} {...p} />;
}

export function LinkButton({
  variant = "secondary",
  size = "md",
  className,
  href,
  ...p
}: Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { variant?: Variant; size?: Size; href: string }) {
  return <Link href={href} className={cx("btn", variantClass[variant], sizeClass[size], className)} {...p} />;
}

/* ------------------------------------------------------------------ class swatch / chips */

export function ClassSwatch({ code, size = "md" }: { code: SuitabilityClassCode; size?: "sm" | "md" }) {
  const m = SUITABILITY_CLASSES[code];
  const dim = size === "sm" ? "size-5 text-[0.6875rem]" : "size-6 text-xs";
  return (
    <span
      aria-hidden="true"
      className={cx("inline-grid shrink-0 place-items-center rounded-xs font-semibold tnum", dim)}
      style={{
        background: m.color,
        color: m.onColor,
        backgroundImage: m.hatch ? "repeating-linear-gradient(135deg, transparent 0 3px, rgb(255 255 255 / 0.35) 3px 4.5px)" : undefined,
      }}
    >
      {code}
    </span>
  );
}

export function ClassChip({ code, short = false }: { code: SuitabilityClassCode; short?: boolean }) {
  const m = SUITABILITY_CLASSES[code];
  return (
    <span className="inline-flex items-center gap-2 text-sm font-medium text-ink">
      <ClassSwatch code={code} />
      <span>
        <span className="visually-hidden">Class {code}: </span>
        {short ? m.short : m.label}
      </span>
    </span>
  );
}

const evidenceGlyph: Record<Evidence, typeof GlyphObserved> = {
  observed: GlyphObserved,
  ml_predicted: GlyphML,
  expert_rule: GlyphRule,
  simulated: GlyphSimulated,
};

/** Evidence class tag: glyph SHAPE + text + border style, never colour alone. The definition is also in the page glossary. */
export function EvidenceBadge({ evidence, className }: { evidence: Evidence; className?: string }) {
  const meta = EVIDENCE_META[evidence] ?? { label: String(evidence ?? "unspecified"), definition: "Evidence class not stated by the data source." };
  const Glyph = evidenceGlyph[evidence] ?? GlyphRule;
  return (
    <span
      title={`${meta.label}: ${meta.definition}`}
      className={cx(
        "inline-flex items-center gap-1 rounded-xs border px-1.5 py-[1px] text-xs font-medium leading-5 text-ink-2",
        evidence === "simulated" ? "border-dashed border-ink-3" : "border-line-strong",
        className,
      )}
    >
      <Glyph className="size-3 shrink-0" />
      {meta.label}
    </span>
  );
}

export function FactorStatusBadge({ status }: { status: FactorStatus }) {
  const color =
    status === "favourable" ? "text-ok" : status === "marginal" ? "text-warn" : "text-danger";
  const mark = status === "favourable" ? "●" : status === "marginal" ? "▲" : status === "limiting" ? "■" : "◆";
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-xs font-semibold", color)}>
      <span aria-hidden="true">{mark}</span>
      {FACTOR_STATUS_META[status].label}
    </span>
  );
}

/* ------------------------------------------------------------------ meters */

export function Meter({
  value,
  label,
  max = 1,
  color = "var(--accent)",
  className,
}: {
  value: number;
  label: string;
  max?: number;
  color?: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <span
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Number(value.toFixed(3))}
      className={cx("block h-1.5 overflow-hidden rounded-xs bg-[color-mix(in_oklab,var(--ink)_14%,transparent)]", className)}
    >
      <span className="block h-full rounded-xs" style={{ inlineSize: `${pct}%`, background: color }} />
    </span>
  );
}

/* ------------------------------------------------------------------ disclosure */

export function Disclosure({
  summary,
  children,
  defaultOpen = false,
  className,
  summaryClassName,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  summaryClassName?: string;
}) {
  return (
    <details open={defaultOpen} className={cx("group", className)}>
      <summary
        className={cx(
          "flex min-h-10 cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden",
          summaryClassName,
        )}
      >
        <span>{summary}</span>
        <IconChevronDown className="size-4 shrink-0 text-ink-3 transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="pb-1 pt-2">{children}</div>
    </details>
  );
}

/* ------------------------------------------------------------------ form helpers */

export function FieldLabel({ htmlFor, children, hint }: { htmlFor: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-semibold text-ink">
        {children}
      </label>
      {hint ? <p className="mt-0.5 text-xs text-ink-3">{hint}</p> : null}
    </div>
  );
}

export function Segmented<T extends string>({
  legend,
  name,
  value,
  onChange,
  options,
}: {
  legend: string;
  name: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; disabled?: boolean; hint?: string }[];
}) {
  return (
    <fieldset className="m-0 min-w-0 border-0 p-0">
      <legend className="visually-hidden">{legend}</legend>
      <div className="grid auto-cols-fr grid-flow-col gap-px overflow-hidden rounded-sm border border-line-strong bg-line-strong">
        {options.map((o) => (
          <label
            key={o.value}
            className={cx(
              "relative flex min-h-10 cursor-pointer items-center justify-center px-3 text-center text-sm font-semibold transition-colors duration-150 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:-outline-offset-2 has-[:focus-visible]:outline-focus",
              value === o.value ? "bg-accent text-on-accent" : "bg-sunken text-ink-2 hover:text-ink",
              o.disabled && "cursor-not-allowed opacity-50",
            )}
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={value === o.value}
              disabled={o.disabled}
              onChange={() => onChange(o.value)}
              className="absolute inset-0 size-full cursor-[inherit] opacity-0"
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function CheckRow({
  id,
  checked,
  onChange,
  children,
  disabled,
  describedBy,
}: {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  children: ReactNode;
  disabled?: boolean;
  describedBy?: string;
}) {
  return (
    <label htmlFor={id} className={cx("flex min-h-9 cursor-pointer items-center gap-2.5 py-1 text-sm text-ink", disabled && "cursor-not-allowed opacity-55")}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-describedby={describedBy}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 shrink-0"
      />
      {children}
    </label>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cx("skeleton", className)} />;
}

/** Key-value row used in detail panels. */
export function KV({ k, children, className }: { k: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cx("grid grid-cols-[minmax(0,9.5rem)_1fr] items-baseline gap-x-3 gap-y-0.5 border-b border-line py-2 text-sm last:border-b-0", className)}>
      <dt className="text-ink-3">{k}</dt>
      <dd className="m-0 min-w-0 text-ink">{children}</dd>
    </div>
  );
}
