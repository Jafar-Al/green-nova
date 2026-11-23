import type { Metadata } from "next";
import { LandView } from "@/components/views/LandView";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Land unit ${decodeURIComponent(id)}`,
    description: "Land details: coordinates, area, current suitability, soil, terrain, water indicators, restoration potential, confidence, limitations and recommendations.",
    robots: { index: false, follow: true },
  };
}

export default async function Page({ params }: Props) {
  const { id } = await params;
  return <LandView id={decodeURIComponent(id)} />;
}
