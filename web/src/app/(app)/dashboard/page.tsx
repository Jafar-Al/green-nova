import type { Metadata } from "next";
import { IS_DEMO_MODE } from "@/lib/config";
import { DashboardView } from "@/components/views/DashboardView";

export const metadata: Metadata = {
  title: "Intelligence dashboard",
  description: IS_DEMO_MODE
    ? "Interactive satellite map with land suitability and restoration potential layers for all 12 governorates of Jordan. Currently showing clearly labelled demonstration data."
    : "Interactive satellite map with land suitability and restoration potential layers for all 12 governorates of Jordan. Every value carries its evidence class and confidence.",
  alternates: { canonical: "/dashboard" },
};

export default function Page() {
  return <DashboardView />;
}
