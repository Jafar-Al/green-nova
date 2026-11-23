import type { Metadata } from "next";
import { IS_DEMO_MODE } from "@/lib/config";
import { DashboardView } from "@/components/views/DashboardView";

export const metadata: Metadata = {
  title: "Intelligence dashboard",
  description: IS_DEMO_MODE
    ? "Interactive satellite map with land suitability and restoration potential layers for Jordan, starting with Ma’an Governorate. Currently showing clearly labelled demonstration data."
    : "Interactive satellite map with land suitability and restoration potential layers for Jordan, starting with Ma’an Governorate. Every value carries its evidence class and confidence.",
  alternates: { canonical: "/dashboard" },
};

export default function Page() {
  return <DashboardView />;
}
