// Each floor of the map is a layer of the AGI's code, and every room you clear
// takes you one deeper; its core waits at the bottom. Beating it opens act 2:
// below the code lies the model itself, with a second core under that.
const LAYERS = ["/ui", "/api", "/auth", "/svc", "/cache", "/queue", "/db", "/vm", "/os", "/bios", "/fw"];
const MODEL_LAYERS = ["/tok", "/emb", "/attn", "/mlp", "/norm", "/grad", "/loss", "/w", "/w2", "/w3"];

export function layerLabel(floor: number, numFloors: number, act = 1): string {
  if (floor >= numFloors - 1) return act > 1 ? "/self" : "/core";
  return (act > 1 ? MODEL_LAYERS : LAYERS)[floor] ?? `/L${floor}`;
}

export function numFloorsOf(nodes: Record<string, { floor: number }>): number {
  return Math.max(0, ...Object.values(nodes).map((n) => n.floor)) + 1;
}
