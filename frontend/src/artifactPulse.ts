import type { Artifact } from "./api";

// Which artifacts a combat log line shows at work - read from combat.py's
// wording, matched to the artifact field behind it. The artifacts arrive with
// all their fields (models.Artifact), more than the Artifact type spells out.
const LINES: [RegExp, string][] = [
  [/Your artifacts strike first/, "opening_damage"],
  [/The attack backfires/, "thorns"],
  [/Your artifacts raise \d+ block/, "turn_block"],
  [/You leech \d+ integrity/, "lifesteal"],
  [/^Logic Bomb:|Logic Bomb: /, "banish_malware"],
  [/Your daemons spread/, "turret_malware"],
  [/Your permanents hold \d+ block over/, "retain_block"],
];

export function firingArtifacts(lines: string[], artifacts: Artifact[]): string[] {
  const fields = new Set(lines.flatMap((line) => LINES.filter(([re]) => re.test(line)).map(([, field]) => field)));
  if (fields.size === 0) return [];
  return artifacts
    .filter((artifact) => {
      const values = artifact as unknown as Record<string, unknown>;
      return [...fields].some((field) => typeof values[field] === "number" && (values[field] as number) !== 0);
    })
    .map((artifact) => artifact.id);
}
