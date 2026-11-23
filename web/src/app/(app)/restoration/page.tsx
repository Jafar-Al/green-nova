import type { Metadata } from "next";
import { IS_DEMO_MODE } from "@/lib/config";
import { RestorationView } from "@/components/views/RestorationView";

export const metadata: Metadata = {
  title: "Restoration potential",
  description: IS_DEMO_MODE
    ? "Select currently unsuitable land, set constraints, compare restoration scenarios, interventions and water-requirement ranges, and export a report. Outcomes are simulated scenarios; currently demonstration data."
    : "Select currently unsuitable land, set constraints, compare restoration scenarios, interventions and water-requirement ranges, and export a report. Outcomes are simulated scenarios, never observed results.",
  alternates: { canonical: "/restoration" },
};

export default function Page() {
  return <RestorationView />;
}
