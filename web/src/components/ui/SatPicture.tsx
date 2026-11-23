/**
 * Responsive satellite image with AVIF/WebP/JPEG sources produced by web/scripts/imagery/render_assets.py.
 * Intrinsic width/height are always set (no layout shift). Provenance for each image is in docs/ASSETS.md.
 */
export function SatPicture({
  name,
  widths,
  width,
  height,
  sizes,
  alt,
  priority = false,
  className,
  style,
}: {
  name: string;
  widths: number[];
  /** Intrinsic size of the largest file. */
  width: number;
  height: number;
  sizes: string;
  alt: string;
  priority?: boolean;
  className?: string;
  style?: React.CSSProperties;
}) {
  const set = (ext: string) => widths.map((w) => `/img/${name}-${w}.${ext} ${w}w`).join(", ");
  const mid = widths[Math.floor(widths.length / 2)] ?? widths[0];
  return (
    <picture>
      <source type="image/avif" srcSet={set("avif")} sizes={sizes} />
      <source type="image/webp" srcSet={set("webp")} sizes={sizes} />
      <img
        src={`/img/${name}-${mid}.jpg`}
        srcSet={set("jpg")}
        sizes={sizes}
        width={width}
        height={height}
        alt={alt}
        decoding={priority ? "sync" : "async"}
        loading={priority ? "eager" : "lazy"}
        fetchPriority={priority ? "high" : "auto"}
        className={className}
        style={style}
      />
    </picture>
  );
}
