import type { Metadata } from "next";
import { IS_DEMO_MODE } from "@/lib/config";
import { SuitabilityView } from "@/components/views/SuitabilityView";

export const metadata: Metadata = {
  title: "Land suitability",
  description: IS_DEMO_MODE
    ? "Select a governorate, start a suitability analysis, inspect individual land polygons with area in hectares and dunums, confidence and the factors behind each class. Currently demonstration data."
    : "Select a governorate, load the suitability analysis, inspect individual land polygons with area in hectares and dunums, confidence and the factors behind each class.",
  alternates: { canonical: "/suitability" },
};

export default function Page() {
  return <SuitabilityView />;
}
