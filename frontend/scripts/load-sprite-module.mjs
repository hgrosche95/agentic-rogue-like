// Shared loader for the sprite tests: the sprite code is TypeScript with
// extensionless imports, which node cannot resolve on its own, so it is bundled
// into self-contained ESM chunks in a temp dir and imported from there.
//
// rolldown is a devDependency of this package (see package.json), not something
// a test may assume from vite's internals.
import { rolldown } from "rolldown";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { dirname, join, resolve } from "path";
import { pathToFileURL } from "url";

const FRONTEND = resolve(import.meta.dirname, "..");

// inputs: { [name]: path relative to frontend/ }, e.g.
//   { sprite: "src/pixel/enemySprite.ts", palette: "src/pixel/palette.ts" }
// Returns { [name]: module }. Modules shared between inputs stay one chunk, so
// every test reads the same palette the sprite itself was drawn with.
export async function loadSpriteModules(inputs) {
  const dir = mkdtempSync(join(tmpdir(), "sprite-test-"));
  try {
    const bundle = await rolldown({
      input: Object.fromEntries(Object.entries(inputs).map(([name, path]) => [name, resolve(FRONTEND, path)])),
      platform: "node",
    });
    const { output } = await bundle.generate({ format: "esm", entryFileNames: "entry-[name].js", chunkFileNames: "chunk-[name].js" });
    for (const chunk of output) {
      if (typeof chunk.code !== "string") continue;
      const file = join(dir, chunk.fileName);
      mkdirSync(dirname(file), { recursive: true });
      writeFileSync(file, chunk.code);
    }
    const mods = {};
    for (const name of Object.keys(inputs)) {
      const chunk = output.find((o) => o.isEntry && o.name === name) || output[0];
      mods[name] = await import(pathToFileURL(join(dir, chunk.fileName)).href);
    }
    return mods;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
