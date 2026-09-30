// The one fixed palette of the pixel arena. Every pixel the scene draws is
// one of these colors, addressed by index - no gradients, no blending. Built
// from the UI's rift colors: violet night, warm lab wood and brass, cyan for
// the machine world, magenta/amber for the lab's magic, plus a few ramps for
// the procedurally drawn enemies.

export const COLORS = [
  // 0-5 night and ink
  "#07051a", // 0 ink (outlines)
  "#110c2e", // 1 deep night
  "#1b1447", // 2 night
  "#271d63", // 3 violet
  "#3a2d8c", // 4 violet light
  "#5a4ab8", // 5 lavender
  // 6-10 lab wood
  "#1c100e", // 6
  "#2c1914", // 7
  "#42271c", // 8
  "#5d3924", // 9
  "#7e5232", // 10
  // 11-15 metal, brass, copper
  "#3a3548", // 11 iron
  "#6d6682", // 12 steel
  "#a86f2a", // 13 brass dark
  "#e0ad52", // 14 brass
  "#ffe29a", // 15 brass highlight
  // 16-18 skin
  "#7a4638", // 16
  "#c98068", // 17
  "#f0b896", // 18
  // 19-21 coat, hair
  "#8e88ad", // 19 coat shadow
  "#d8d3ea", // 20 coat
  "#fbf8ff", // 21 white
  // 22-25 cyan (machine world)
  "#0a4e66", // 22
  "#138fb0", // 23
  "#3fd6e8", // 24
  "#bff8ff", // 25
  // 26-28 magenta
  "#6e1466", // 26
  "#d13cbe", // 27
  "#ff8ae6", // 28
  // 29-31 amber
  "#b2481a", // 29
  "#ff9a3d", // 30
  "#ffd36b", // 31
  // 32-34 green (heal)
  "#1c6b45", // 32
  "#3ee08a", // 33
  "#b6ffcf", // 34
  // 35-36 red
  "#8a1030", // 35
  "#ff4f8b", // 36
  // 37-39 pants, dark cloth
  "#1f1a26", // 37
  "#352c40", // 38
  "#4a3f58", // 39
  // 40-69 enemy body ramps: 10 ramps of dark / mid / light
  "#2e2016", "#6b4a2c", "#a8804a", // 40 horns: bark
  "#26301a", "#56682c", "#93a848", // 43 horns: moss
  "#3a0f44", "#8a2a9c", "#d46be6", // 46 circuits: magenta
  "#0c3a40", "#1c8a8c", "#5ad8c8", // 49 circuits: teal
  "#16381a", "#3c8a2c", "#8ad85a", // 52 tentacles: green
  "#2a1654", "#5a3aa8", "#9a7ae6", // 55 tentacles: purple
  "#0c2a48", "#1c5c94", "#4aa0dc", // 58 fins: sea blue
  "#0c3638", "#1c7872", "#48c0b0", // 61 fins: teal
  "#48101c", "#a8283c", "#ec6070", // 64 stripes: red
  "#48300c", "#a8781c", "#ecc050", // 67 stripes: gold
] as const;

export type ColorIndex = number;

// named indices for the drawing code
export const C = {
  ink: 0,
  deepNight: 1,
  night: 2,
  violet: 3,
  violetLight: 4,
  lavender: 5,
  wood0: 6,
  wood1: 7,
  wood2: 8,
  wood3: 9,
  wood4: 10,
  iron: 11,
  steel: 12,
  brassDark: 13,
  brass: 14,
  brassHi: 15,
  skinShade: 16,
  skin: 17,
  skinHi: 18,
  coatShade: 19,
  coat: 20,
  white: 21,
  cyanDark: 22,
  cyanMid: 23,
  cyan: 24,
  cyanHi: 25,
  magentaDark: 26,
  magenta: 27,
  magentaHi: 28,
  amberDark: 29,
  amber: 30,
  amberHi: 31,
  greenDark: 32,
  green: 33,
  greenHi: 34,
  redDark: 35,
  red: 36,
  cloth0: 37,
  cloth1: 38,
  cloth2: 39,
  enemyRamps: 40,
} as const;

// Particle color ramps: a particle steps through its ramp from hot to dark
// over its life (white -> magic color -> dark), then despawns.
export const RAMPS: readonly (readonly ColorIndex[])[] = [
  [C.white, C.cyanHi, C.cyan, C.cyanMid, C.cyanDark], // 0 cyan
  [C.white, C.amberHi, C.amber, C.amberDark, C.wood2], // 1 amber
  [C.white, C.magentaHi, C.magenta, C.magentaDark, C.violet], // 2 magenta
  [C.white, C.greenHi, C.green, C.greenDark, C.night], // 3 green
  [C.white, C.red, C.redDark, C.violet], // 4 red
  [C.white, C.brassHi, C.brass, C.brassDark], // 5 brass
  [C.white, C.steel, C.iron, C.night], // 6 steel
  [C.white, C.lavender, C.violetLight, C.violet], // 7 violet
];

export const RAMP = { cyan: 0, amber: 1, magenta: 2, green: 3, red: 4, brass: 5, steel: 6, violet: 7 } as const;
