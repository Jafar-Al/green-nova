import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/config";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return ["", "/dashboard", "/suitability", "/restoration"].map((p) => ({
    url: `${SITE_URL}${p}`,
    lastModified: now,
    changeFrequency: p === "" ? "monthly" : "weekly",
    priority: p === "" ? 1 : 0.7,
  }));
}
