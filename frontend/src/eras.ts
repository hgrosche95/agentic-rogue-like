// Each floor of the map is an era on the timeline you jump through; the
// boss waits at the end of time. Beating it opens act 2: the far future,
// with a second end of time behind it.
const YEARS = ["1969", "1984", "1999", "2012", "2031", "2049", "2077", "2099", "2150", "2250", "2400"];
const FAR_YEARS = ["2150", "2300", "2500", "2800", "3200", "4000", "6000", "9999"];

export function eraLabel(floor: number, numFloors: number, act = 1): string {
  if (floor >= numFloors - 1) return act > 1 ? `Ω${act}` : "Ω";
  return (act > 1 ? FAR_YEARS : YEARS)[floor] ?? `+${floor}`;
}

export function numFloorsOf(nodes: Record<string, { floor: number }>): number {
  return Math.max(0, ...Object.values(nodes).map((n) => n.floor)) + 1;
}
