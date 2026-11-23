"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { getProvider } from "./providers";
import type { DataProvider } from "./types";

export const useProvider = (): DataProvider => getProvider();

export type AsyncState<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: Error };

const LOADING = { status: "loading", data: null, error: null } as const;

/**
 * Minimal async loader with reload. A fresh token is minted whenever the deps (or a reload) change, so "loading" is
 * derived during render and results of superseded calls are ignored, without setting state synchronously in an effect.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> & { reload: () => void } {
  const [req, setReq] = useState(() => ({ deps, token: Symbol("request") }));
  const [result, setResult] = useState<{ token: symbol; value: AsyncState<T> } | null>(null);
  // "storing information from previous renders": mint a new token when the deps change (derived state, no effect needed)
  let cur = req;
  if (req.deps.length !== deps.length || req.deps.some((d, i) => !Object.is(d, deps[i]))) {
    cur = { deps, token: Symbol("request") };
    setReq(cur);
  }
  const token = cur.token;
  useEffect(() => {
    let alive = true;
    fn().then(
      (data) => alive && setResult({ token, value: { status: "success", data, error: null } }),
      (e: unknown) => alive && setResult({ token, value: { status: "error", data: null, error: e instanceof Error ? e : new Error(String(e)) } }),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  const reload = useCallback(() => setReq((r) => ({ deps: r.deps, token: Symbol("request") })), []);
  const value: AsyncState<T> = result && result.token === token ? result.value : LOADING;
  return { ...value, reload };
}

/** Online/offline state (navigator.onLine + events). SSR-safe: assumes online. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("online", cb);
      window.addEventListener("offline", cb);
      return () => {
        window.removeEventListener("online", cb);
        window.removeEventListener("offline", cb);
      };
    },
    () => navigator.onLine,
    () => true,
  );
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia("(prefers-reduced-motion: reduce)");
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

/** Triggers a browser download for an in-memory file. */
export function downloadText(filename: string, mime: string, content: string): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Media query as an external store: server snapshot is `serverValue`, the client corrects it right after hydration. */
export function useMediaQuery(query: string, serverValue = true): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => serverValue,
  );
}
