// Tiny building blocks for procedural sounds: an enveloped oscillator and an
// enveloped, filtered noise burst. Every sound in the game is made from these
// (plus the bit crusher from the engine), so nothing has to be downloaded.

import type { AudioGraph } from "./engine";

export interface ToneOptions {
  type?: OscillatorType;
  freq: number;
  // glides exponentially to this frequency over the tone's duration
  to?: number;
  dur: number;
  gain?: number;
  attack?: number;
  detune?: number;
  // optional low-pass cutoff, gliding to `filterTo`
  filter?: number;
  filterTo?: number;
  q?: number;
  // node to play into, defaults to the effects bus
  dest?: AudioNode;
}

// Linear attack, exponential decay to silence at t + dur.
function envelope(ctx: AudioContext, t: number, dur: number, peak: number, attack: number): GainNode {
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0.0001, t);
  gain.gain.linearRampToValueAtTime(peak, t + Math.min(attack, dur * 0.5));
  gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  return gain;
}

export function tone(g: AudioGraph, t: number, o: ToneOptions): void {
  const { ctx } = g;
  const osc = ctx.createOscillator();
  osc.type = o.type ?? "sine";
  osc.frequency.setValueAtTime(o.freq, t);
  if (o.to !== undefined) osc.frequency.exponentialRampToValueAtTime(Math.max(1, o.to), t + o.dur);
  if (o.detune) osc.detune.value = o.detune;

  let tail: AudioNode = osc;
  if (o.filter !== undefined) {
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.Q.value = o.q ?? 1;
    filter.frequency.setValueAtTime(o.filter, t);
    if (o.filterTo !== undefined) filter.frequency.exponentialRampToValueAtTime(o.filterTo, t + o.dur);
    tail = tail.connect(filter);
  }
  tail.connect(envelope(ctx, t, o.dur, o.gain ?? 0.3, o.attack ?? 0.005)).connect(o.dest ?? g.sfx);
  osc.start(t);
  osc.stop(t + o.dur + 0.02);
}

export interface NoiseOptions {
  dur: number;
  gain?: number;
  attack?: number;
  filter?: BiquadFilterType;
  freq?: number;
  to?: number;
  q?: number;
  // bits for the crusher; leave out for clean noise
  crush?: number;
  dest?: AudioNode;
}

export function noise(g: AudioGraph, t: number, o: NoiseOptions): void {
  const { ctx } = g;
  const src = ctx.createBufferSource();
  src.buffer = g.noise;
  // start somewhere random so back-to-back bursts don't sound identical
  const offset = Math.random() * (g.noise.duration - o.dur - 0.05);

  const filter = ctx.createBiquadFilter();
  filter.type = o.filter ?? "bandpass";
  filter.Q.value = o.q ?? 1;
  filter.frequency.setValueAtTime(o.freq ?? 2000, t);
  if (o.to !== undefined) filter.frequency.exponentialRampToValueAtTime(o.to, t + o.dur);

  let tail: AudioNode = src.connect(filter);
  if (o.crush !== undefined) tail = tail.connect(g.crusher(o.crush));
  tail.connect(envelope(ctx, t, o.dur, o.gain ?? 0.3, o.attack ?? 0.002)).connect(o.dest ?? g.sfx);
  src.start(t, Math.max(0, offset), o.dur + 0.05);
}

// A short run of pitch-stepped square blips - the "data" in a data burst.
export function glitch(g: AudioGraph, t: number, dur: number, gain: number, low = 300, high = 2400): void {
  const step = 0.018;
  for (let at = 0; at < dur; at += step) {
    tone(g, t + at, {
      type: "square",
      freq: low + Math.random() * (high - low),
      dur: step * 1.1,
      gain: gain * (1 - (at / dur) * 0.6),
      attack: 0.001,
    });
  }
}
