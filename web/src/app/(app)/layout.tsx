import { AppHeader } from "@/components/layout/AppHeader";

/** Workspace routes (dashboard, suitability, restoration, land details): dark charcoal theme with the sticky app header. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="theme-dark min-h-[calc(100dvh-var(--demo-h))]">
      <AppHeader />
      {children}
    </div>
  );
}
