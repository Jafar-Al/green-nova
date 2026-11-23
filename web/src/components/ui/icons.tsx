import type { SVGProps } from "react";

/** One icon family: 24px grid, 1.6 stroke, round caps. Decorative by default (aria-hidden); pair with visible text. */
function Svg({ children, ...p }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...p}
    >
      {children}
    </svg>
  );
}

export const IconArrowRight = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M4 12h15M13 6l6 6-6 6" />
  </Svg>
);
export const IconDownload = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
  </Svg>
);
export const IconLayers = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </Svg>
);
export const IconInfo = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </Svg>
);
export const IconAlert = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M12 3.5 2.8 19.5h18.4L12 3.5Z" />
    <path d="M12 10v4.5M12 17.2h.01" />
  </Svg>
);
export const IconCheck = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </Svg>
);
export const IconClose = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);
export const IconOffline = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M3 3l18 18M8.5 8.8A10 10 0 0 0 3 12M12 6a14 14 0 0 1 9 3.5M7 14a7 7 0 0 1 3-1.8M16.5 14.2A7 7 0 0 0 14 12.7M12 19h.01" />
  </Svg>
);
export const IconPlay = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M7 4.5v15l12-7.5-12-7.5Z" />
  </Svg>
);
export const IconStop = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <rect x="6" y="6" width="12" height="12" rx="1.5" />
  </Svg>
);
export const IconChevronDown = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
);
export const IconExternal = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Svg>
);
export const IconMap = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="m9 4 6 2 5-2v14l-5 2-6-2-5 2V6l5-2Z" />
    <path d="M9 4v14M15 6v14" />
  </Svg>
);
export const IconFilter = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M4 6h16M7 12h10M10 18h4" />
  </Svg>
);
export const IconRefresh = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M20 5v5h-5M4 19v-5h5" />
    <path d="M6.3 9A7 7 0 0 1 19 10M17.7 15A7 7 0 0 1 5 14" />
  </Svg>
);

/* Evidence glyphs: distinct SHAPES so evidence never relies on colour alone */
export const GlyphObserved = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="6" fill="currentColor" stroke="none" />
  </Svg>
);
export const GlyphML = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <path d="M12 5.5 18.5 12 12 18.5 5.5 12 12 5.5Z" />
  </Svg>
);
export const GlyphRule = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p}>
    <rect x="6" y="6" width="12" height="12" rx="1.5" />
  </Svg>
);
export const GlyphSimulated = (p: SVGProps<SVGSVGElement>) => (
  <Svg {...p} strokeDasharray="2.6 2.6">
    <circle cx="12" cy="12" r="6.2" />
  </Svg>
);
