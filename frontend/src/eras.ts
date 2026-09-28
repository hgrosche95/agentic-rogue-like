// Each floor of the map is an era on the timeline you jump through; the
// boss waits at the end of time.
const YEARS = ["1969", "1984", "1999", "2012", "2031", "2049", "2077", "2099", "2150", "2250", "2400"];

export function eraLabel(floor: number, numFloors: number): string {
  if (floor >= numFloors - 1) return "Ω";
  return YEARS[floor] ?? `+${floor}`;
}

export function numFloorsOf(nodes: Record<string, { floor: number }>): number {
  return Math.max(0, ...Object.values(nodes).map((n) => n.floor)) + 1;
}
