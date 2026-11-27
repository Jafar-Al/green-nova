import type { DataProvider } from "../types";
import { createApiProvider } from "./api";
import { createDemoProvider } from "./demo";

export { createApiProvider } from "./api";
export { createDemoProvider, DEMO_REGION_ID } from "./demo";

let singleton: DataProvider | null = null;

/**
 * Provider selected by NEXT_PUBLIC_DATA_PROVIDER: "api" (the build default, set in next.config.ts) uses the real models through the BFF;
 * "demo" is an explicit opt-in for UI development and is never selected implicitly or as a fallback. One instance per page session. The api provider only ever calls same-origin relative URLs (BFF route handlers);
 * it never learns the FastAPI address.
 */
export function getProvider(): DataProvider {
  if (singleton) return singleton;
  singleton = process.env.NEXT_PUBLIC_DATA_PROVIDER === "api" ? createApiProvider() : createDemoProvider();
  return singleton;
}
