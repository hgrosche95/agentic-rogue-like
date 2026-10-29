// The game's terms, each with a short definition - one place for every text
// that marks them (RichText) and for the tooltip that explains them
// (Tooltips). The UI calls the piles Source / Cache / Purged, the card texts
// say draw pile / graveyard / banished - the definitions tie them together.

export interface Keyword {
  id: string;
  // the name the tooltip heads its definition with
  term: string;
  // what it matches in running text (case-insensitive) - the piles' own
  // names are left out, too common a word to mark in flavor text
  pattern: RegExp;
  text: string;
}

export const KEYWORDS: Keyword[] = [
  {
    id: "permanent",
    term: "Permanent",
    pattern: /\bpermanents?\b/,
    text: "Stays in play and keeps working every turn. Classic: takes a slot on the field. Program: runs in the background, as many as you play.",
  },
  {
    id: "one-shot",
    term: "One-shot",
    pattern: /\bone-shot\b/,
    text: "Banished after it is played - gone for the rest of the fight, back in the next one. Marked 1× on the card.",
  },
  {
    id: "graveyard",
    term: "Graveyard (Cache)",
    pattern: /\bgraveyard\b/,
    text: "Played and discarded cards land here. When Source runs dry, it is shuffled back in.",
  },
  {
    id: "banished",
    term: "Banished (Purged)",
    pattern: /\bbanished\b/,
    text: "Gone for the rest of the fight. One-shot cards end up here; they are back next fight.",
  },
  {
    id: "banish",
    term: "Banish",
    pattern: /\bbanish(?:es)?\b/,
    text: "Send a card from your hand to Purged: gone for the rest of the fight, back next fight. You pick which. Every banished card feeds Payload and Garbage Collect.",
  },
  {
    id: "source",
    term: "Source",
    pattern: /\bdraw pile\b/,
    text: "Your draw pile. You draw from it at the start of every turn; empty, the Cache is shuffled back in.",
  },
  {
    id: "block",
    term: "Block",
    pattern: /\bblock\b/,
    text: "Absorbs incoming damage before your HP. It lasts until your next turn.",
  },
  {
    id: "armor",
    term: "Armor",
    pattern: /\barmor\b/,
    text: "Takes that much off every hit you take, for the whole fight.",
  },
  {
    id: "atk",
    term: "ATK",
    pattern: /\(\+ATK\)|\bATK\b/,
    text: "Your attack stat. Attack cards marked (+ATK) add it to their damage.",
  },
  {
    id: "boost",
    term: "Boost",
    pattern: /\bmore effective\b|\boverclock(?:ed)?\b/,
    text: "Overclock-style permanents multiply the numbers of action cards. Classic: the slots to their right. Program: every line.",
  },
  {
    id: "daemon",
    term: "Daemon",
    pattern: /\bdaemons?\b|\bend of turn\b/,
    text: "A permanent that acts on its own at the end of every turn, before the enemy moves.",
  },
  {
    id: "control-flow",
    term: "Control flow",
    pattern: /\bcontrol flow\b/,
    text: "Program mode: queued like an action, does nothing itself but steers the actions around it when the program runs - order matters.",
  },
  {
    id: "fork",
    term: "Fork",
    pattern: /\bfork\b/,
    text: "Control flow: the next action to its right runs twice.",
  },
  {
    id: "loop",
    term: "Loop",
    pattern: /\bloop\b/,
    text: "Control flow: the last action to its left runs once more.",
  },
  {
    id: "if-wounded",
    term: "If Wounded",
    pattern: /\bif wounded\b/,
    text: "Control flow: the next action runs twice if the enemy is at half HP or less by then.",
  },
  {
    id: "pipe",
    term: "Pipe",
    pattern: /\bpipe\b/,
    text: "Control flow (Vibe-Coder): the next action gets a bonus for every action that already ran.",
  },
  {
    id: "batch",
    term: "Batch",
    pattern: /\bbatch\b/,
    text: "Control flow (Vibe-Coder): frees used tokens for every action still to run.",
  },
  {
    id: "hot-path",
    term: "Hot Path",
    pattern: /\bhot path\b/,
    text: "An artifact: the card in its gold line runs as its upgraded version.",
  },
  {
    id: "interrupt",
    term: "Interrupt",
    pattern: /\binterrupt(?:s|ed)?\b/,
    text: "Enemy move: only your first lines run this turn - the cut ones go to the graveyard unused. Put what matters first.",
  },
  {
    id: "refactor",
    term: "Refactor",
    pattern: /\brefactor(?:s|ed)?\b/,
    text: "Boss move: your program runs right to left this turn - Fork and Loop then steer the lines to their left.",
  },
  {
    id: "malware",
    term: "Malware",
    pattern: /\bmalware\b|\binfect(?:s|ed)?\b/,
    text: "The infected side loses that much HP at the end of each turn, then one stack fades. Ignores block.",
  },
  {
    id: "exposed",
    term: "Exposed",
    pattern: /\bexpose[ds]?\b/,
    text: "Attack cards deal 50% more to it, for that many turns.",
  },
  {
    id: "throttled",
    term: "Throttled",
    pattern: /\bthrottle[ds]?\b/,
    text: "It deals 25% less, for that many of its turns.",
  },
  {
    id: "tokens",
    term: "Tokens",
    pattern: /\btokens?\b|\bcontext window\b/,
    text: "Vibe-Coder: cards cost tokens from the context window, and some free up every turn. Past the window, a card may hallucinate.",
  },
  {
    id: "hallucinate",
    term: "Hallucination",
    pattern: /\bhallucinat\w*/,
    text: "A card played past the context window may misfire - an attack hits you, a block or heal goes to the enemy.",
  },
  {
    id: "glitch",
    term: "Glitch",
    pattern: /\bglitch(?:es)?\b/,
    text: "A dead card the enemy slips into your deck. Play it to flush it out for this fight.",
  },
  {
    id: "intent",
    term: "Intent",
    pattern: /\bintent\b/,
    text: "The mark over the enemy and the badge in its HUD: the move it makes when you end the turn.",
  },
];

const BY_ID = new Map(KEYWORDS.map((k) => [k.id, k]));

export function keyword(id: string): Keyword | undefined {
  return BY_ID.get(id);
}

// every term at once, for splitting a text; and each one on its own, anchored,
// to tell which term a match was
export const ANY_KEYWORD = new RegExp(KEYWORDS.map((k) => k.pattern.source).join("|"), "gi");
const ANCHORED = KEYWORDS.map((k) => ({ k, re: new RegExp(`^(?:${k.pattern.source})$`, "i") }));

export function keywordFor(word: string): Keyword | undefined {
  return ANCHORED.find(({ re }) => re.test(word))?.k;
}
