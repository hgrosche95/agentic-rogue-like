// Virtual clock for frame-exact capture: timers, rAF and CSS/Web animations
// only move when the recorder calls window.__advance(ms).
(() => {
  let now = performance.now();
  const perfBase = now;
  const dateBase = Date.now();
  const RealDate = Date;
  let timers = [];
  let rafs = [];
  let nextId = 1;
  performance.now = () => now;
  Date.now = () => dateBase + (now - perfBase);
  window.setTimeout = (fn, ms = 0, ...args) => {
    const t = { id: nextId++, at: now + Math.max(0, +ms || 0), fn, args };
    timers.push(t);
    return t.id;
  };
  window.setInterval = (fn, ms = 0, ...args) => {
    const every = Math.max(1, +ms || 0);
    const t = { id: nextId++, at: now + every, fn, args, every };
    timers.push(t);
    return t.id;
  };
  window.clearTimeout = window.clearInterval = (id) => {
    timers = timers.filter((t) => t.id !== id);
  };
  window.requestAnimationFrame = (fn) => {
    const id = nextId++;
    rafs.push({ id, fn });
    return id;
  };
  window.cancelAnimationFrame = (id) => {
    rafs = rafs.filter((r) => r.id !== id);
  };
  const starts = new WeakMap();
  function syncAnimations() {
    for (const a of document.getAnimations()) {
      let s = starts.get(a);
      if (s === undefined) {
        const ct = typeof a.currentTime === "number" ? a.currentTime : 0;
        s = now - ct / (a.playbackRate || 1);
        starts.set(a, s);
        if (a.playState === "running") a.pause();
      }
      if (a.playState === "finished" || a.__done) continue;
      if (a.playState === "running") a.pause();
      const local = (now - s) * (a.playbackRate || 1);
      let end = Infinity;
      try {
        end = a.effect ? a.effect.getComputedTiming().endTime : Infinity;
      } catch {}
      try {
        if (local >= end) {
          a.__done = true;
          a.finish();
        } else {
          a.currentTime = local;
        }
      } catch {}
    }
  }
  window.__advance = (dt) => {
    const target = now + dt;
    for (let guard = 0; guard < 10000; guard++) {
      timers.sort((a, b) => a.at - b.at);
      const t = timers[0];
      if (!t || t.at > target) break;
      now = Math.max(now, t.at);
      if (t.every) t.at += t.every;
      else timers.shift();
      try {
        typeof t.fn === "function" ? t.fn(...t.args) : eval(t.fn);
      } catch (e) {
        console.error(e);
      }
    }
    now = target;
    const rs = rafs;
    rafs = [];
    for (const r of rs) {
      try {
        r.fn(now);
      } catch (e) {
        console.error(e);
      }
    }
    syncAnimations();
  };
  window.__syncAnimations = syncAnimations;
  void RealDate;
})();
