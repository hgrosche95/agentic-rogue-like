// Sound effects. Dr. Chronos fights by typing shell commands, so his cards
// sound digital - keyboard clatter, then a glitch, a synth hum or a disk seek
// depending on the card - never steel on steel.

import type { CardType } from "../api";
import { audio, midiToFreq, type AudioGraph } from "./engine";
import { glitch, noise, tone } from "./synth";

export type SfxName =
  // typing the command in
  | "typing"
  | "enter"
  // one per kind of card, played once the command runs
  | "attack"
  | "final_strike"
  | "block"
  | "heal"
  | "draw"
  | "retrieve"
  | "restore"
  | "permanent"
  | "daemon_tick"
  // the fight
  | "impact"
  | "enemy_attack"
  | "player_hit"
  | "block_absorb"
  | "enemy_defeated"
  | "victory"
  | "defeat"
  // cards and UI
  | "reward_open"
  | "reward_pick"
  | "hover"
  | "select"
  | "card_flight"
  | "map_select"
  | "click"
  | "error";

export interface SfxOptions {
  // attack: how many times the card hits
  hits?: number;
  // typing: how long the professor types, in ms
  durationMs?: number;
  // start this many ms from now
  delayMs?: number;
}

type Sound = (g: AudioGraph, t: number, o: SfxOptions) => void;

function keyClick(g: AudioGraph, t: number, gain = 0.14) {
  // the plastic clack of a mechanical key: a bright noise tick over a tiny thump
  noise(g, t, { dur: 0.025, gain, filter: "highpass", freq: 2500 + Math.random() * 2500, q: 0.7 });
  tone(g, t, { type: "triangle", freq: 1100 + Math.random() * 700, dur: 0.02, gain: gain * 0.35, attack: 0.001 });
}

function enter(g: AudioGraph, t: number) {
  // the big key: longer, lower, with the bottom-out thud
  noise(g, t, { dur: 0.05, gain: 0.22, filter: "bandpass", freq: 1500, q: 0.8 });
  tone(g, t, { type: "sine", freq: 190, to: 90, dur: 0.07, gain: 0.25, attack: 0.001 });
}

// One strike of an attack: a descending saw zap into a crushed data burst.
function dataStrike(g: AudioGraph, t: number, gain: number) {
  tone(g, t, { type: "sawtooth", freq: 2200, to: 110, dur: 0.14, gain: gain * 0.5, filter: 6000, filterTo: 800 });
  noise(g, t, { dur: 0.12, gain: gain * 0.6, filter: "bandpass", freq: 3000, to: 500, q: 1.2, crush: 3 });
  glitch(g, t + 0.01, 0.09, gain * 0.18);
}

const SOUNDS: Record<SfxName, Sound> = {
  typing(g, t, { durationMs = 600 }) {
    // the clicks spread over the typing time with a human, uneven rhythm
    const dur = durationMs / 1000;
    const keys = Math.max(4, Math.round(dur * 16));
    for (let i = 0; i < keys; i++) {
      const at = (i / keys) * dur * 0.92 + Math.random() * 0.02;
      keyClick(g, t + at, 0.09 + Math.random() * 0.06);
    }
  },
  enter(g, t) {
    enter(g, t);
  },

  attack(g, t, { hits = 1 }) {
    const count = Math.max(1, Math.min(hits, 6));
    // several hits come as a volley of quick, slightly rising pulses
    const gap = count > 1 ? 0.1 : 0;
    for (let i = 0; i < count; i++) {
      dataStrike(g, t + i * gap, count > 1 ? 0.75 : 1);
      if (count > 1) tone(g, t + i * gap, { type: "square", freq: 440 * 1.12 ** i, dur: 0.05, gain: 0.08 });
    }
  },
  final_strike(g, t) {
    // KERNEL PANIC: a crushed crash, the machine's error beeps and a dead hum
    noise(g, t, { dur: 0.7, gain: 0.55, filter: "lowpass", freq: 6000, to: 200, q: 0.5, crush: 2 });
    tone(g, t, { type: "square", freq: 110, to: 28, dur: 0.8, gain: 0.35, filter: 1800, filterTo: 120 });
    tone(g, t, { type: "sawtooth", freq: 1400, to: 60, dur: 0.35, gain: 0.25 });
    glitch(g, t + 0.05, 0.3, 0.12, 80, 900);
    [880, 660, 440].forEach((freq, i) =>
      tone(g, t + 0.35 + i * 0.12, { type: "square", freq, dur: 0.09, gain: 0.1, attack: 0.001 }),
    );
    // the bluescreen: a flat mains hum that simply stops
    tone(g, t + 0.75, { type: "sawtooth", freq: 50, dur: 0.45, gain: 0.14, attack: 0.001, filter: 400 });
  },
  block(g, t) {
    // firewall up: a detuned low synth swelling like a shield
    for (const detune of [-8, 8]) {
      tone(g, t, { type: "sawtooth", freq: 110, dur: 0.6, gain: 0.16, attack: 0.08, detune, filter: 250, filterTo: 1400, q: 6 });
    }
    tone(g, t, { type: "sine", freq: 55, dur: 0.6, gain: 0.3, attack: 0.05 });
    tone(g, t + 0.05, { type: "triangle", freq: 1320, dur: 0.35, gain: 0.05, attack: 0.05 });
  },
  heal(g, t) {
    // hotfix applied: a friendly rising major arpeggio
    [72, 76, 79, 84, 88].forEach((note, i) =>
      tone(g, t + i * 0.065, { type: "triangle", freq: midiToFreq(note), dur: 0.35, gain: 0.16, attack: 0.004 }),
    );
    tone(g, t + 0.3, { type: "sine", freq: midiToFreq(96), dur: 0.5, gain: 0.05 });
  },
  draw(g, t) {
    // the disk head seeking: accelerating ticks over a spin-up whirr
    tone(g, t, { type: "sawtooth", freq: 180, to: 520, dur: 0.4, gain: 0.07, filter: 900 });
    let at = 0;
    for (let gap = 0.06; at < 0.38; gap *= 0.82) {
      noise(g, t + at, { dur: 0.012, gain: 0.16, filter: "bandpass", freq: 3200, q: 3 });
      at += gap;
    }
  },
  retrieve(g, t) {
    // rollback: a tape rewinding - a warbling, falling squeal
    const lfo = g.ctx.createOscillator();
    const depth = g.ctx.createGain();
    lfo.frequency.value = 22;
    depth.gain.value = 60;
    lfo.connect(depth);
    const osc = g.ctx.createOscillator();
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(1600, t);
    osc.frequency.exponentialRampToValueAtTime(300, t + 0.45);
    depth.connect(osc.frequency);
    const env = g.ctx.createGain();
    env.gain.setValueAtTime(0.0001, t);
    env.gain.linearRampToValueAtTime(0.08, t + 0.03);
    env.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
    const filter = g.ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 2500;
    osc.connect(filter).connect(env).connect(g.sfx);
    osc.start(t);
    lfo.start(t);
    osc.stop(t + 0.55);
    lfo.stop(t + 0.55);
    noise(g, t, { dur: 0.45, gain: 0.08, filter: "bandpass", freq: 4000, to: 1200, q: 2 });
    enter(g, t + 0.48);
  },
  restore(g, t) {
    // undelete: rewind, then the file coming back with a chime
    SOUNDS.retrieve(g, t, {});
    tone(g, t + 0.5, { type: "triangle", freq: midiToFreq(81), dur: 0.3, gain: 0.12 });
    tone(g, t + 0.58, { type: "triangle", freq: midiToFreq(88), dur: 0.4, gain: 0.12 });
  },
  permanent(g, t) {
    // a process starting: a rising hum and the two-tone POST beep
    tone(g, t, { type: "sawtooth", freq: 60, to: 240, dur: 0.35, gain: 0.1, filter: 300, filterTo: 1500 });
    tone(g, t + 0.12, { type: "square", freq: 1000, dur: 0.08, gain: 0.09, attack: 0.001 });
    tone(g, t + 0.26, { type: "square", freq: 1500, dur: 0.14, gain: 0.09, attack: 0.001 });
  },
  daemon_tick(g, t) {
    // the daemon's end-of-turn shot: a short, bright zap
    tone(g, t, { type: "sawtooth", freq: 2600, to: 500, dur: 0.07, gain: 0.18, attack: 0.001 });
    noise(g, t, { dur: 0.04, gain: 0.12, filter: "highpass", freq: 3000, crush: 4 });
  },

  impact(g, t) {
    // the blow landing on the enemy
    noise(g, t, { dur: 0.1, gain: 0.3, filter: "lowpass", freq: 2500, to: 300, crush: 3 });
    tone(g, t, { type: "square", freq: 120, to: 50, dur: 0.12, gain: 0.2 });
  },
  enemy_attack(g, t) {
    // a low, rushing growl from the rift
    noise(g, t, { dur: 0.4, gain: 0.3, filter: "lowpass", freq: 250, to: 1600, q: 4 });
    tone(g, t, { type: "sawtooth", freq: 85, to: 45, dur: 0.4, gain: 0.18, filter: 600 });
  },
  player_hit(g, t) {
    // a dull hit and the monitor crackling
    tone(g, t, { type: "sine", freq: 160, to: 45, dur: 0.22, gain: 0.45, attack: 0.001 });
    noise(g, t, { dur: 0.18, gain: 0.25, filter: "lowpass", freq: 1800, to: 200, crush: 4 });
  },
  block_absorb(g, t) {
    // the attack deflecting off the firewall
    tone(g, t, { type: "sine", freq: 660, dur: 0.35, gain: 0.15, attack: 0.001 });
    tone(g, t, { type: "sine", freq: 991, dur: 0.25, gain: 0.1, attack: 0.001 });
    noise(g, t, { dur: 0.08, gain: 0.15, filter: "bandpass", freq: 5000, q: 2 });
  },
  enemy_defeated(g, t) {
    // the enemy de-rezzing: a crushed glide down and a burst of static
    tone(g, t, { type: "square", freq: 900, to: 40, dur: 0.8, gain: 0.18, filter: 3000, filterTo: 200 });
    noise(g, t + 0.05, { dur: 0.7, gain: 0.25, filter: "bandpass", freq: 3000, to: 300, q: 0.7, crush: 2 });
    glitch(g, t + 0.1, 0.4, 0.06);
  },
  victory(g, t) {
    // a little 8-bit fanfare
    [60, 64, 67, 72].forEach((note, i) =>
      tone(g, t + i * 0.11, { type: "square", freq: midiToFreq(note), dur: 0.14, gain: 0.1, filter: 3000 }),
    );
    for (const note of [72, 76, 79]) {
      tone(g, t + 0.45, { type: "square", freq: midiToFreq(note), dur: 0.9, gain: 0.07, filter: 2500, filterTo: 800 });
    }
  },
  defeat(g, t) {
    // a slow minor fall and the system powering down
    [69, 65, 62, 57].forEach((note, i) =>
      tone(g, t + i * 0.28, { type: "square", freq: midiToFreq(note), dur: 0.35, gain: 0.09, filter: 1600 - i * 300 }),
    );
    tone(g, t + 1.1, { type: "sawtooth", freq: 220, to: 30, dur: 1.4, gain: 0.12, filter: 800, filterTo: 80 });
  },

  reward_open(g, t) {
    // loot on the screen: a sparkle up the scale
    [84, 88, 91, 96].forEach((note, i) =>
      tone(g, t + i * 0.05, { type: "triangle", freq: midiToFreq(note), dur: 0.22, gain: 0.07 }),
    );
  },
  reward_pick(g, t) {
    tone(g, t, { type: "square", freq: 880, dur: 0.07, gain: 0.08, attack: 0.001 });
    tone(g, t + 0.07, { type: "square", freq: 1320, dur: 0.12, gain: 0.08, attack: 0.001 });
    tone(g, t + 0.12, { type: "triangle", freq: midiToFreq(96), dur: 0.4, gain: 0.07 });
  },
  hover(g, t) {
    tone(g, t, { type: "sine", freq: 2400, dur: 0.018, gain: 0.03, attack: 0.001 });
  },
  select(g, t) {
    tone(g, t, { type: "square", freq: 1200, to: 1500, dur: 0.035, gain: 0.06, attack: 0.001 });
  },
  card_flight(g, t) {
    noise(g, t, { dur: 0.3, gain: 0.1, filter: "bandpass", freq: 500, to: 3500, q: 1.5, attack: 0.08 });
  },
  map_select(g, t) {
    // a route plotted on the terminal: a tick, then two confirming beeps
    noise(g, t, { dur: 0.015, gain: 0.12, filter: "bandpass", freq: 3200, q: 3 });
    tone(g, t + 0.03, { type: "square", freq: 660, dur: 0.06, gain: 0.07, attack: 0.001 });
    tone(g, t + 0.1, { type: "square", freq: 990, dur: 0.1, gain: 0.07, attack: 0.001 });
  },
  click(g, t) {
    tone(g, t, { type: "square", freq: 900, dur: 0.03, gain: 0.05, attack: 0.001 });
  },
  error(g, t) {
    for (const at of [0, 0.14]) tone(g, t + at, { type: "square", freq: 110, dur: 0.1, gain: 0.1, filter: 900 });
  },
};

const lastPlayed = new Map<SfxName, number>();

export const sfx = {
  play(name: SfxName, options: SfxOptions = {}) {
    const g = audio();
    if (!g) return;
    // the same sound twice within a few ms is one event reported twice
    // (StrictMode's double effects, two handlers for one click) - and would
    // only come out as one louder, phasey sound anyway
    const now = performance.now();
    if (now - (lastPlayed.get(name) ?? -Infinity) < 30) return;
    lastPlayed.set(name, now);
    const t = g.ctx.currentTime + 0.005 + (options.delayMs ?? 0) / 1000;
    SOUNDS[name](g, t, options);
  },
};

// The effect a card makes once its typed command runs.
export function cardSound(type: CardType): SfxName {
  switch (type) {
    case "attack":
    case "final_strike":
    case "block":
    case "heal":
    case "draw":
    case "retrieve":
    case "restore":
      return type;
    // wiping the field and pulling the banished pile back sounds like both
    case "reboot":
      return "restore";
    case "amplifier":
    case "armor":
    case "draw_bonus":
    case "damage_boost":
    case "turret":
    case "fortify":
      return "permanent";
  }
}

// The API doesn't send an attack's hit count, but its text always says it
// ("Hit 3 times ...", "Hit twice ...").
export function hitsOf(description: string): number {
  const match = /\bhit (\d+|twice|three times)\b/i.exec(description);
  if (!match) return 1;
  const word = match[1].toLowerCase();
  if (word === "twice") return 2;
  if (word === "three times") return 3;
  return Number(word);
}
