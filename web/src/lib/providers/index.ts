import type { DataProvider } from "../types";
import { createApiProvider } from "./api";
import { createDemoProvider } from "./demo";

export { createApiProvider } from "./api";
export { createDemoProvider, DEMO_REGION_ID } from "./demo";

let singleton: DataProvider | null = null;

/**
 * Provider selected by NEXT_PUBLIC_DATA_PROVIDER ("demo" default, "api" in Phase C).
 * One instance per page session. The api provider only ever calls same-origin relative URLs (BFF route handlers);
 * it never learns the FastAPI address.
 */
export function getProvider(): DataProvider {
  if (singleton) return singleton;
  singleton = process.env.NEXT_PUBLIC_DATA_PROVIDER === "api" ? createApiProvider() : createDemoProvider();
  return singleton;
}
