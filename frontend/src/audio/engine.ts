// The shared Web Audio graph: one AudioContext, a master gain and one bus
// each for music and sound effects, plus the player's audio settings.
//
// Browsers only let a page make sound after the user interacted with it, so
// the context is created lazily on the first pointer or key press (see
// unlockAudio) - until then every sound request is silently dropped and the
// music just remembers which mood it should start in.

export interface AudioSettings {
  muted: boolean;
  // 0..1, scaled down again on the buses so "full" still sits under speech level
  music: number;
  sfx: number;
}

const SETTINGS_KEY = "agentic-rogue-like:audio";
const DEFAULT_SETTINGS: AudioSettings = { muted: false, music: 0.5, sfx: 0.7 };
// headroom: the buses never go past these, whatever the sliders say
const MUSIC_MAX = 0.8;
const SFX_MAX = 0.65;

function loadSettings(): AudioSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<AudioSettings>;
    const volume = (v: unknown, fallback: number) =>
      typeof v === "number" && Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : fallback;
    return {
      muted: parsed.muted === true,
      music: volume(parsed.music, DEFAULT_SETTINGS.music),
      sfx: volume(parsed.sfx, DEFAULT_SETTINGS.sfx),
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function saveSettings(settings: AudioSettings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // Storage blocked (private mode) - the settings just don't survive a reload.
  }
}

let settings = loadSettings();
const listeners = new Set<() => void>();

export interface AudioGraph {
  ctx: AudioContext;
  music: GainNode;
  sfx: GainNode;
  noise: AudioBuffer;
  crusher: (bits: number) => WaveShaperNode;
}

let graph: AudioGraph | null = null;
let master: GainNode | null = null;
const readyCallbacks: ((graph: AudioGraph) => void)[] = [];

export function getSettings(): AudioSettings {
  return settings;
}

export function subscribeSettings(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function updateSettings(patch: Partial<AudioSettings>) {
  settings = { ...settings, ...patch };
  saveSettings(settings);
  applyLevels(0.08);
  for (const listener of listeners) listener();
}

function applyLevels(glide: number) {
  if (!graph || !master) return;
  const now = graph.ctx.currentTime;
  master.gain.setTargetAtTime(settings.muted ? 0 : 1, now, glide);
  graph.music.gain.setTargetAtTime(settings.music * settings.music * MUSIC_MAX, now, glide);
  graph.sfx.gain.setTargetAtTime(settings.sfx * settings.sfx * SFX_MAX, now, glide);
}

// The graph, or null while the browser still holds audio back. Callers that
// only want to fire a sound use this and give up on null.
export function audio(): AudioGraph | null {
  if (!graph || graph.ctx.state !== "running" || settings.muted) return null;
  return graph;
}

// Runs `callback` once the graph exists (at once if it already does).
export function whenReady(callback: (graph: AudioGraph) => void) {
  if (graph) callback(graph);
  else readyCallbacks.push(callback);
}

function crusherCurve(bits: number): Float32Array<ArrayBuffer> {
  const steps = 2 ** bits;
  const curve = new Float32Array(1024);
  for (let i = 0; i < curve.length; i++) {
    const x = (i / (curve.length - 1)) * 2 - 1;
    curve[i] = Math.round(x * steps) / steps;
  }
  return curve;
}

function createGraph(): AudioGraph | null {
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  const ctx = new Ctor();
  master = ctx.createGain();
  // A gentle limiter so stacked hits and the boss loop never clip.
  const limiter = ctx.createDynamicsCompressor();
  limiter.threshold.value = -10;
  limiter.knee.value = 6;
  limiter.ratio.value = 8;
  limiter.attack.value = 0.003;
  limiter.release.value = 0.2;
  master.connect(limiter).connect(ctx.destination);

  const music = ctx.createGain();
  const sfx = ctx.createGain();
  music.gain.value = 0;
  sfx.gain.value = 0;
  music.connect(master);
  sfx.connect(master);

  const noise = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
  const data = noise.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;

  const curves = new Map<number, Float32Array<ArrayBuffer>>();
  const crusher = (bits: number) => {
    const shaper = ctx.createWaveShaper();
    let curve = curves.get(bits);
    if (!curve) {
      curve = crusherCurve(bits);
      curves.set(bits, curve);
    }
    shaper.curve = curve;
    return shaper;
  };

  return { ctx, music, sfx, noise, crusher };
}

// Hooks the first user gesture that may start audio. Call once at startup.
export function unlockAudio() {
  const events = ["pointerdown", "keydown", "touchstart"] as const;
  const unlock = () => {
    if (!graph) {
      graph = createGraph();
      if (!graph) return;
      applyLevels(0.4);
      const ready = graph;
      readyCallbacks.splice(0).forEach((callback) => callback(ready));
    }
    void graph.ctx.resume();
    for (const event of events) window.removeEventListener(event, unlock, true);
  };
  for (const event of events) window.addEventListener(event, unlock, true);

  // A hidden tab throttles timers, which would make the music stumble -
  // pause the whole context instead and pick up where it left off.
  document.addEventListener("visibilitychange", () => {
    if (!graph) return;
    if (document.hidden) void graph.ctx.suspend();
    else void graph.ctx.resume();
  });
}

export function midiToFreq(midi: number): number {
  return 440 * 2 ** ((midi - 69) / 12);
}
