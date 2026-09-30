// Where things stand in the pixel arena, in logical pixels. The HTML overlays
// (combat log, intent marker, damage numbers) are placed from these, as
// percentages of the logical frame, so they line up at every scale.

export const WIDTH = 240;
export const HEIGHT = 100;

// the floor line both fighters stand on
export const FLOOR = 86;

// the rift between the lab (left) and the machine world (right)
export const RIFT_X = 120;

// Dr. Chronos' feet, and his keyboard on its pult in front of him
export const PLAYER_X = 54;
export const KEYBOARD = { x: 67, y: 62, w: 12 };

// the enemy's feet
export const ENEMY_X = 184;

// the monitor glass hanging over the rift - the combat log is drawn over it
export const MONITOR = { x: 80, y: 6, w: 80, h: 32 };

export const pct = {
  x: (x: number) => `${((x / WIDTH) * 100).toFixed(3)}%`,
  y: (y: number) => `${((y / HEIGHT) * 100).toFixed(3)}%`,
};
