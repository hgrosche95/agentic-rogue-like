// Background music: small chiptune/synthwave loops sequenced live with Web
// Audio - a calm terminal loop for the map, intro and events, a driving one
// for fights and a harder, faster one for the boss. Changing the mood
// crossfades from the running loop into the next one.

import { getSettings, midiToFreq, whenReady, type AudioGraph } from "./engine";
import { noise, tone } from "./synth";

export type Mood = "map" | "combat" | "boss" | "silence";

interface Bar {
  bass: number;
  chord: number[];
}

interface Song {
  bpm: number;
  bars: Bar[];
  // plays whatever falls on one 16th note
  step(g: AudioGraph, dest: AudioNode, t: number, step: number, bar: Bar, sixteenth: number): void;
}

function kick(g: AudioGraph, dest: AudioNode, t: number, gain: number) {
  tone(g, t, { type: "sine", freq: 150, to: 42, dur: 0.2, gain, attack: 0.001, dest });
}

function snare(g: AudioGraph, dest: AudioNode, t: number, gain: number) {
  noise(g, t, { dur: 0.14, gain, filter: "bandpass", freq: 1900, q: 0.8, dest });
  tone(g, t, { type: "triangle", freq: 190, to: 140, dur: 0.08, gain: gain * 0.6, attack: 0.001, dest });
}

function hat(g: AudioGraph, dest: AudioNode, t: number, gain: number, open = false) {
  noise(g, t, { dur: open ? 0.12 : 0.03, gain, filter: "highpass", freq: 7500, q: 0.7, dest });
}

function pad(g: AudioGraph, dest: AudioNode, t: number, notes: number[], dur: number, gain: number, cutoff: number) {
  for (const note of notes) {
    for (const detune of [-7, 7]) {
      tone(g, t, {
        type: "sawtooth",
        freq: midiToFreq(note),
        detune,
        dur,
        gain,
        attack: dur * 0.35,
        filter: cutoff,
        filterTo: cutoff * 0.5,
        dest,
      });
    }
  }
}

// The map/intro loop: slow A minor pads, a soft 8th-note arpeggio and a
// sine bass - a terminal humming to itself.
const MAP: Song = {
  bpm: 84,
  bars: [
    { bass: 45, chord: [57, 60, 64] },
    { bass: 41, chord: [57, 60, 65] },
    { bass: 48, chord: [55, 60, 64] },
    { bass: 43, chord: [55, 59, 62] },
  ],
  step(g, dest, t, step, bar, s) {
    const barDur = s * 16;
    if (step === 0) pad(g, dest, t, bar.chord, barDur * 1.1, 0.022, 900);
    if (step === 0 || step === 8) {
      tone(g, t, { type: "sine", freq: midiToFreq(bar.bass), dur: barDur * 0.45, gain: 0.2, attack: 0.02, dest });
    }
    if (step % 2 === 0) {
      const order = [0, 1, 2, 1, 2, 0, 1, 2];
      const note = bar.chord[order[step / 2]] + 12;
      tone(g, t, { type: "triangle", freq: midiToFreq(note), dur: s * 2.5, gain: 0.045, attack: 0.005, dest });
    }
    if (step === 4 || step === 12) hat(g, dest, t, 0.018);
  },
};

// The fight loop: four-on-the-floor, a pumping octave saw bass and a square
// arpeggio racing over D minor - Bb - C - A.
const COMBAT: Song = {
  bpm: 116,
  bars: [
    { bass: 38, chord: [62, 65, 69] },
    { bass: 34, chord: [62, 65, 70] },
    { bass: 36, chord: [60, 64, 67] },
    { bass: 33, chord: [61, 64, 69] },
  ],
  step(g, dest, t, step, bar, s) {
    if (step % 4 === 0) kick(g, dest, t, 0.42);
    if (step === 4 || step === 12) snare(g, dest, t, 0.13);
    if (step % 2 === 0) hat(g, dest, t, 0.035, step % 4 === 2);
    if (step % 2 === 0) {
      const octave = step % 4 === 2 ? 12 : 0;
      tone(g, t, {
        type: "sawtooth",
        freq: midiToFreq(bar.bass + octave),
        dur: s * 1.7,
        gain: 0.11,
        attack: 0.003,
        filter: 1100,
        filterTo: 250,
        q: 4,
        dest,
      });
    }
    const note = bar.chord[step % 3] + 12 * (1 + (step >> 3) % 2);
    tone(g, t, { type: "square", freq: midiToFreq(note), dur: s * 0.9, gain: 0.022, attack: 0.002, filter: 2800, dest });
    if (step === 0) pad(g, dest, t, bar.chord, s * 16, 0.012, 1400);
  },
};

// The boss loop: faster and darker - E Phrygian, a galloping 16th bass, a
// busier kick, 16th hats and an alarm-like lead every other bar.
const BOSS: Song = {
  bpm: 132,
  bars: [
    { bass: 40, chord: [52, 55, 59] },
    { bass: 41, chord: [53, 57, 60] },
    { bass: 40, chord: [52, 55, 59] },
    { bass: 39, chord: [51, 54, 57] },
  ],
  step(g, dest, t, step, bar, s) {
    if ([0, 3, 6, 8, 11, 14].includes(step)) kick(g, dest, t, 0.45);
    if (step === 4 || step === 12) snare(g, dest, t, 0.16);
    hat(g, dest, t, step % 2 === 0 ? 0.035 : 0.02);
    tone(g, t, {
      type: "sawtooth",
      freq: midiToFreq(bar.bass + (step % 4 === 2 ? 12 : 0)),
      dur: s * 0.95,
      gain: 0.1,
      attack: 0.002,
      filter: 1400,
      filterTo: 300,
      q: 6,
      dest,
    });
    const note = bar.chord[(step * 2) % 3] + 24;
    tone(g, t, { type: "square", freq: midiToFreq(note), dur: s * 0.8, gain: 0.02, attack: 0.002, filter: 3500, dest });
    if (step === 0) pad(g, dest, t, bar.chord.map((n) => n + 12), s * 16, 0.012, 1800);
    // the alarm: a wailing minor second, on the first bar of each pair
    if (bar === BOSS.bars[0] || bar === BOSS.bars[2]) {
      if (step === 0) {
        tone(g, t, { type: "square", freq: midiToFreq(76), to: midiToFreq(77), dur: s * 6, gain: 0.03, filter: 2200, dest });
      }
      if (step === 8) {
        tone(g, t, { type: "square", freq: midiToFreq(77), to: midiToFreq(76), dur: s * 6, gain: 0.03, filter: 2200, dest });
      }
    }
  },
};

const SONGS: Record<Exclude<Mood, "silence">, Song> = { map: MAP, combat: COMBAT, boss: BOSS };

interface Track {
  mood: Mood;
  song: Song;
  gain: GainNode;
  nextTime: number;
  step: number;
  // context time after which a fading track is torn down
  endAt: number | null;
}

const LOOKAHEAD = 0.15;
const FADE = 0.7; // time constant of the crossfade, ~3x this until inaudible

let tracks: Track[] = [];
let mood: Mood = "silence";
let timer: number | null = null;

function schedule(g: AudioGraph) {
  const now = g.ctx.currentTime;
  const silent = getSettings().muted || getSettings().music === 0;
  for (const track of tracks) {
    const sixteenth = 60 / track.song.bpm / 4;
    // after a suspended tab the clock jumps - skip ahead instead of catching up
    if (track.nextTime < now - 0.5) track.nextTime = now + 0.05;
    while (track.nextTime < now + LOOKAHEAD) {
      const bar = track.song.bars[Math.floor(track.step / 16) % track.song.bars.length];
      if (!silent) track.song.step(g, track.gain, track.nextTime, track.step % 16, bar, sixteenth);
      track.nextTime += sixteenth;
      track.step++;
    }
  }
  tracks = tracks.filter((track) => {
    if (track.endAt === null || now < track.endAt) return true;
    track.gain.disconnect();
    return false;
  });
}

function start(g: AudioGraph) {
  if (timer === null) timer = window.setInterval(() => schedule(g), 30);
  const now = g.ctx.currentTime;
  for (const track of tracks) {
    if (track.endAt !== null) continue;
    track.gain.gain.setTargetAtTime(0, now, FADE);
    track.endAt = now + FADE * 6;
  }
  if (mood === "silence") return;
  const gain = g.ctx.createGain();
  gain.gain.setValueAtTime(0, now);
  gain.gain.setTargetAtTime(1, now, FADE);
  gain.connect(g.music);
  tracks.push({ mood, song: SONGS[mood], gain, nextTime: now + 0.05, step: 0, endAt: null });
}

export const music = {
  setMood(next: Mood) {
    if (next === mood) return;
    mood = next;
    whenReady((g) => {
      // a later setMood may have overtaken this one while audio was locked
      if (mood !== next) return;
      const current = tracks.find((track) => track.endAt === null);
      if (current?.mood === next) return;
      start(g);
    });
  },
};
