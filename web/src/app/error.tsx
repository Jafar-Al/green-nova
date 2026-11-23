"use client";

import { useEffect } from "react";
import { Logo } from "@/components/brand/Logo";
import { Button, LinkButton } from "@/components/ui/primitives";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Phase C: report to the error tracker. Never log user data.
    console.error(error);
  }, [error]);
  return (
    <div className="theme-dark grid min-h-[calc(100dvh-var(--demo-h))] place-items-center px-[var(--spacing-gutter)]">
      <main id="main" tabIndex={-1} role="alert" className="grid max-w-xl gap-6">
        <Logo />
        <div>
          <h1 className="h-page">This view failed to load</h1>
          <p className="lead mt-3">The interface hit an unexpected error. Nothing was changed or sent anywhere. Try again, or return to the overview.</p>
          {error.digest ? <p className="mt-2 text-xs text-ink-3">Reference: {error.digest}</p> : null}
        </div>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary" onClick={reset}>
            Try again
          </Button>
          <LinkButton href="/">Back to overview</LinkButton>
        </div>
      </main>
    </div>
  );
}
