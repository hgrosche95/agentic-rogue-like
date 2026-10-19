import type { CardType, EnemyIntentType, Status } from "./api";

// what a card's readout number counts, per card type
const UNIT: Partial<Record<CardType, string>> = {
  attack: "dmg",
  final_strike: "dmg",
  block: "block",
  heal: "hp",
};

export function unitOf(type: CardType): string | undefined {
  return UNIT[type];
}

// "7" for a sure number, "8–13" for a roll
export function rangeText(min: number, max: number): string {
  return min === max ? `${min}` : `${min}–${max}`;
}

// What an intent is called, its number, and what it means - for the marker
// over the enemy's head and the badge in its HUD. A move with its own name
// (from the enemy's move set) is called by it; the tooltip still says what
// kind of move it is.
export function describeIntent(
  intent: EnemyIntentType,
  min: number,
  max: number,
  hits: number,
  name: string | null = null,
): { label: string; amount: string; title: string } {
  const plain = describeKind(intent, min, max, hits);
  return name ? { ...plain, label: name, title: `${name}: ${plain.title}` } : plain;
}

function describeKind(
  intent: EnemyIntentType,
  min: number,
  max: number,
  hits: number,
): { label: string; amount: string; title: string } {
  const range = rangeText(min, max);
  switch (intent) {
    case "attack":
      return { label: "Attack", amount: range, title: `Attacks next for ${range}` };
    case "defend":
      return { label: "Brace", amount: range, title: `Braces for ${range} block next` };
    case "barrage":
      return {
        label: "Barrage",
        amount: `${hits}×${range}`,
        title: `Hits ${hits} times for ${range} each next - armor counts against every hit`,
      };
    case "charge":
      return {
        label: "Charge",
        amount: `+${range}`,
        title: `Charges up, raising ${range} block - an overload follows on the turn after`,
      };
    case "overload":
      return { label: "Overload", amount: range, title: `Releases a crushing overload for ${range} next` };
    case "purge":
      return {
        label: "Purge",
        amount: range,
        title: `Destroys your rightmost permanent card, then hits for ${range}`,
      };
    case "infect":
      return {
        label: "Infect",
        amount: range,
        title: `Hits for ${range} and leaves Malware on you - it costs HP every turn as it fades`,
      };
    case "lock":
      return {
        label: "Lock",
        amount: range,
        title: `Hits for ${range} and locks one of your empty field slots for your next turn`,
      };
    case "corrupt":
      return {
        label: "Corrupt",
        amount: range,
        title: `Hits for ${range} and shuffles useless Glitch cards into your draw pile`,
      };
  }
}

// What each status does, for the badges' tooltips - see combat.STATUS_DESCRIPTIONS.
export const STATUS_TEXT: Record<Status, string> = {
  malware: "Loses that much HP at the end of each turn, then one stack fades.",
  exposed: "Attack cards deal 50% more to it. Turns left.",
  throttled: "Deals 25% less. Turns left.",
};
