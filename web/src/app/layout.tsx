import type { Metadata, Viewport } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google";
import { DemoBar } from "@/components/layout/DemoBar";
import { SITE_NAME, SITE_TAGLINE, SITE_URL } from "@/lib/config";
import "./globals.css";

/* Self-hosted at build time by next/font (no runtime request to Google). Archivo carries a width axis used for display. */
const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-archivo",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jbmono",
  display: "swap",
});

const DESCRIPTION =
  "GREEN NOVA AI maps where land is suitable for agriculture today and where degraded land could be restored, from satellite imagery, with the evidence behind every number shown. Covers all 12 governorates of Jordan.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: `${SITE_NAME} – Satellite land intelligence for agriculture`, template: `%s · ${SITE_NAME}` },
  description: DESCRIPTION,
  applicationName: SITE_NAME,
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: `${SITE_NAME}. ${SITE_TAGLINE}`,
    description: DESCRIPTION,
    url: SITE_URL,
    images: [{ url: "/img/hero-maan-1600.jpg", width: 1600, height: 896, alt: "Sentinel-2 true-colour view of Ma’an Governorate, Jordan" }],
  },
  twitter: { card: "summary_large_image", title: `${SITE_NAME}. ${SITE_TAGLINE}`, description: DESCRIPTION, images: ["/img/hero-maan-1600.jpg"] },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f2419",
  colorScheme: "dark light",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" dir="ltr" className={`${archivo.variable} ${mono.variable}`}>
      <body>
        <a href="#main" className="skip-link">
          Skip to main content
        </a>
        <DemoBar />
        {children}
      </body>
    </html>
  );
}
