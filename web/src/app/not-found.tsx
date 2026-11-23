import { Logo } from "@/components/brand/Logo";
import { LinkButton } from "@/components/ui/primitives";

export default function NotFound() {
  return (
    <div className="theme-dark grid min-h-[calc(100dvh-var(--demo-h))] place-items-center px-[var(--spacing-gutter)]">
      <main id="main" tabIndex={-1} className="grid max-w-xl gap-6">
        <Logo />
        <div>
          <h1 className="h-page">This page is not on the map</h1>
          <p className="lead mt-3">The address may be mistyped, or the land unit or region it pointed to does not exist in this release.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <LinkButton href="/dashboard" variant="primary">
            Open the dashboard
          </LinkButton>
          <LinkButton href="/">Back to overview</LinkButton>
        </div>
      </main>
    </div>
  );
}
