#!/usr/bin/env node
/**
 * Assemble a self-contained production folder from a finished `next build` (output: "standalone").
 *
 *   node scripts/assemble-standalone.mjs <outDir>
 *
 * Result (no node_modules, no source tree, no OneDrive path needed at runtime):
 *   <outDir>/server.js
 *   <outDir>/.next/static/...      (copied beside the server, as Next requires)
 *   <outDir>/public/...            (imagery, basemap tiles, boundary data)
 *   <outDir>/node_modules/...      (only what the server traced)
 * Run:  PORT=3000 HOSTNAME=0.0.0.0 node server.js   (Windows cmd: set PORT=3000 && set HOSTNAME=0.0.0.0 && node server.js)
 */
import { cpSync, existsSync, mkdirSync, rmSync, statSync, readdirSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const out = path.resolve(process.argv[2] ?? path.join(root, "release"));
const standalone = path.join(root, ".next", "standalone");
const stat = path.join(root, ".next", "static");

if (!existsSync(path.join(standalone, "server.js"))) {
  console.error(`No standalone build at ${standalone}. Run "npm run build" first (next.config.ts sets output: "standalone").`);
  process.exit(1);
}
if (out === root || out.startsWith(path.join(root, ".next"))) {
  console.error("Refusing to write the release into the build tree.");
  process.exit(1);
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync(standalone, out, { recursive: true, dereference: true });
mkdirSync(path.join(out, ".next"), { recursive: true });
cpSync(stat, path.join(out, ".next", "static"), { recursive: true });
cpSync(path.join(root, "public"), path.join(out, "public"), { recursive: true });

const size = (dir) => {
  let n = 0;
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    n += e.isDirectory() ? size(p) : statSync(p).size;
  }
  return n;
};
console.log(`Release assembled at ${out} (${(size(out) / 1e6).toFixed(1)} MB). Start: PORT=3000 HOSTNAME=0.0.0.0 node server.js`);
