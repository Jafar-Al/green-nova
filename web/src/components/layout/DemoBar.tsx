import Link from "next/link";
import { IS_DEMO_MODE } from "@/lib/config";
import { DEMO_NOTICE } from "@/lib/demo/notice";

/**
 * Persistent, visible marker on EVERY route while the demo provider is active (product rule).
 * Sticky so it can never scroll out of view; not dismissible.
 */
export function DemoBar() {
  if (!IS_DEMO_MODE) return null;
  return (
    <div
      role="region"
      aria-label="Data status"
      className="sticky top-0 z-[60] flex items-center justify-center gap-x-4 gap-y-0 px-[var(--spacing-gutter)] text-center text-[0.8125rem] leading-tight text-[#1a1405]"
      style={{
        minBlockSize: "var(--demo-h)",
        background:
          "repeating-linear-gradient(135deg, #ecd48c 0 14px, #e6cb78 14px 28px)",
      }}
    >
      <p className="m-0 py-1 font-bold tracking-wide">
        {DEMO_NOTICE}
        <span className="hidden font-medium sm:inline"> &middot; synthetic records, no model involved</span>
      </p>
      <Link href="/#evidence" className="hidden shrink-0 font-semibold text-[#1a1405] underline md:inline">
        What is real?
      </Link>
    </div>
  );
}
