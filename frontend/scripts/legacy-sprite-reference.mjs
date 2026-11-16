// Locks the "no new fields means exactly the sprite of today" promise (see
// pixel/enemySprite.ts): it bundles the CURRENT build(), draws the legacy path
// (no bodyShape / feature) and the explicit blob path, and checks both against
// fixed reference values that were captured from the pre-change source (commit
// 8f8b0f9).
//
// Not run-against-run: the fingerprints below are pinned, so a regression in the
// blob path fails even if nothing else changed. Run with cwd=frontend, or with
// npm run test:sprites, which lint and CI run. Exits 0 when every fingerprint
// matches, 1 with a diff otherwise.
import { loadSpriteModules } from "./load-sprite-module.mjs";

// fixed inputs covering all five features and both ends of the HP / attack ranges
const SPECS = [
  { name: "Grid Warden", maxHp: 40, attack: 10, setting: "cyber" },
  { name: "Bog Lurker", maxHp: 90, attack: 16, setting: "alien swamp" },
  { name: "Siren", maxHp: 120, attack: 18, setting: "ocean" },
  { name: "Masked Carnival", maxHp: 38, attack: 9, setting: "carnival" },
  { name: "Crypt Fiend", maxHp: 130, attack: 9, setting: "dungeon crypt" },
];

// reference values captured from 8f8b0f9 (the state before body_shape/feature)
const REFERENCE = {
  "Grid Warden": { pixels: "400:5c0d1080", eyes: "3:61a5fe0", top: 40, ramp: 2, body: "46/47/48" },
  "Bog Lurker": { pixels: "1009:b83e4e2b", eyes: "4:1d2550", top: 22, ramp: 3, body: "52/53/54" },
  Siren: { pixels: "1229:2f53ffc4", eyes: "1:1faf85d1", top: 24, ramp: 0, body: "58/59/60" },
  "Masked Carnival": { pixels: "391:a53adcb7", eyes: "3:98f2573f", top: 41, ramp: 1, body: "67/68/69" },
  "Crypt Fiend": { pixels: "1118:bd57fac7", eyes: "1:fd350296", top: 25, ramp: 4, body: "43/44/45" },
};

function fnv(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16);
}

function fingerprint(sprite) {
  const px = sprite.pixels;
  let h = 0x811c9dc5;
  let nz = 0;
  for (let i = 0; i < px.length; i++) {
    h ^= px[i];
    h = Math.imul(h, 0x01000193);
    if (px[i]) nz++;
  }
  const eyeStr = sprite.eyes.map((e) => `${e.x},${e.y},${e.s}`).join(";");
  return {
    pixels: `${nz}:${(h >>> 0).toString(16)}`,
    eyes: `${sprite.eyes.length}:${fnv(eyeStr)}`,
    top: sprite.top,
    ramp: sprite.ramp,
    body: [...sprite.body].join("/"),
  };
}

const { sprite: mod } = await loadSpriteModules({ sprite: "src/pixel/enemySprite.ts" });
let failed = false;
for (const spec of SPECS) {
  const ref = REFERENCE[spec.name];
  const noField = fingerprint(mod.enemySprite({ ...spec }));
  const blob = fingerprint(mod.enemySprite({ ...spec, bodyShape: "blob" }));
  for (const [label, got] of [
    ["no-field", noField],
    ["blob", blob],
  ]) {
    if (JSON.stringify(got) !== JSON.stringify(ref)) {
      failed = true;
      console.error(`MISMATCH ${spec.name} (${label})\n  expected: ${JSON.stringify(ref)}\n  got     : ${JSON.stringify(got)}`);
    }
  }
}

if (failed) {
  console.error("FAIL: the legacy sprite path changed against the pinned reference values.");
  process.exit(1);
}
console.log(`OK: legacy path matches the pinned reference for ${SPECS.length} specs.`);
