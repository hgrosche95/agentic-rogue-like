// Bounds test for every body shape (see pixel/enemySprite.ts): each one must
// draw a 64*64 sprite whose pixels hold valid palette colors, whose top is the
// first filled row, and whose eyes are non-empty and fully on the canvas. The
// shapes meant to stand do so on the arena floor, the ghost floats. Run at
// both ends of the HP and attack ranges, early game and boss.
// Run with cwd=frontend, or with npm run test:sprites, which lint and CI run.
// Exits 0 when every check passes, 1 with the failed checks otherwise.
import { loadSpriteModules } from "./load-sprite-module.mjs";

const { sprite: mod, shape: shapeMod, palette: paletteMod } = await loadSpriteModules({
  sprite: "src/pixel/enemySprite.ts",
  shape: "src/components/enemyShape.ts",
  palette: "src/pixel/palette.ts",
});

const SIZE = 64;
const FLOOR = SIZE - 1;
// all values of the BodyShape type in components/enemyShape.ts
const BODY_SHAPES = ["blob", "swarm", "brute", "machine", "ghost", "serpent"];
// a setting that themes as "circuits": markings only, no feature geometry, so
// the bounds checks below hold for every shape the same way
const SETTING = "cyber lab";

const failures = [];
const fail = (name, check) => failures.push(`${name}: ${check}`);

for (const bodyShape of BODY_SHAPES) {
  for (const [label, maxHp, attack] of [
    ["min", shapeMod.HP_RANGE[0], shapeMod.ATTACK_RANGE[0]],
    ["max", shapeMod.HP_RANGE[1], shapeMod.ATTACK_RANGE[1]],
  ]) {
    const name = `${bodyShape}/${label}`;
    const s = mod.enemySprite({ name, maxHp, attack, setting: SETTING, bodyShape });

    if (s.w !== SIZE || s.h !== SIZE || s.pixels.length !== SIZE * SIZE) {
      fail(name, `not 64x64: ${s.w}x${s.h}, ${s.pixels.length} pixels`);
      continue;
    }
    // every drawn pixel must address a real palette color (stored index + 1)
    let firstRow = -1;
    let lastRow = -1;
    let badColor = -1;
    for (let y = 0; y < SIZE; y++) {
      for (let x = 0; x < SIZE; x++) {
        const v = s.pixels[y * SIZE + x];
        if (v > paletteMod.COLORS.length) badColor = v;
        if (!v) continue;
        if (firstRow < 0) firstRow = y;
        lastRow = y;
      }
    }
    if (badColor >= 0) fail(name, `pixel value ${badColor} is beyond the palette (1..${paletteMod.COLORS.length})`);
    if (firstRow < 0) {
      fail(name, "the sprite is empty");
      continue;
    }
    if (s.top !== firstRow) fail(name, `top is ${s.top}, first filled row is ${firstRow}`);
    if (s.eyes.length === 0) fail(name, "the sprite has no eyes");
    for (const e of s.eyes) {
      if (e.x < 0 || e.y < 0 || e.x + e.s > SIZE || e.y + e.s > SIZE) {
        fail(name, `eye at (${e.x}, ${e.y}) size ${e.s} reaches off the canvas`);
      }
    }
    // the shapes meant to stand on the floor do, like the blob's (their outline
    // adds one row below the body); the ghost is the shape allowed to float,
    // the swarm's small bodies sit spread over the canvas, not on the floor
    if (bodyShape === "ghost") {
      if (lastRow > FLOOR - 8) fail(name, `the ghost reaches row ${lastRow} instead of floating`);
    } else if (bodyShape !== "swarm" && lastRow < FLOOR - 1) {
      fail(name, `the body ends at row ${lastRow}, not on the floor`);
    }
  }
}

if (failures.length) {
  for (const f of failures) console.error(`FAIL ${f}`);
  process.exit(1);
}
console.log(`shape sprite bounds ok: ${BODY_SHAPES.length} shapes x 2 stat extremes`);
