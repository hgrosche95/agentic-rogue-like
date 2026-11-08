// The game's terms, each with a short definition - one place for every text
// that marks them (RichText) and for the tooltip that explains them
// (Tooltips). The game says Source / Graveyard / Banished / Integrity / Credits
// everywhere; the tooltip terms carry the plain word next to them.

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
    term: "Graveyard · discard pile",
    pattern: /\b(?:your|the) graveyard\b/,
    text: "Played and discarded cards land here. When Source runs dry, it is shuffled back in.",
  },
  {
    id: "banished",
    term: "Banished · out of the fight",
    pattern: /\bbanished\b/,
    text: "Gone for the rest of the fight. One-shot cards end up here; they are back next fight.",
  },
  {
    id: "banish",
    term: "Banish",
    pattern: /\bbanish(?:es)?\b/,
    text: "Send a card from your hand to Banished: gone for the rest of the fight, back next fight. You pick which. Every banished card feeds Payload and Garbage Collect.",
  },
  {
    id: "instant",
    term: "Instant",
    pattern: /\binstant\b/,
    text: "Takes effect the moment you play it - it never waits in a program line.",
  },
  {
    id: "source",
    term: "Source · draw pile",
    pattern: /\b(?:your|the) source\b/,
    text: "Your draw pile. You draw from it at the start of every turn; empty, the Graveyard is shuffled back in.",
  },
  {
    id: "integrity",
    term: "Integrity · your HP",
    pattern: /\bmax integrity\b/,
    text: "Your hit points. Damage takes it down, heals bring it back - at 0 the run ends.",
  },
  {
    id: "block",
    term: "Block",
    pattern: /\bblock\b/,
    text: "Absorbs incoming damage before your integrity. It lasts until your next turn.",
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
    id: "goto",
    term: "Goto 1",
    pattern: /\bgoto 1\b|\bjumps back to line 1\b/,
    text: "Control flow: once it runs, the program jumps back to line 1 and the first actions that ran before it run again - each from its own line, so a Bootstrap is the first line once more.",
  },
  {
    id: "if-wounded",
    term: "If Wounded",
    pattern: /\bif wounded\b/,
    text: "Control flow: the next action runs twice if the enemy is at half integrity or less by then.",
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
    id: "try-catch",
    term: "Try/Catch",
    pattern: /\btry\/catch\b/,
    text: "Control flow: the lines after it can't be interrupted - an enemy's Interrupt no longer cuts them.",
  },
  {
    id: "buffer",
    term: "Buffer",
    pattern: /\bbuffer\b|\bstored? (its |their )?damage\b/,
    text: "Control flow: the next action's damage is stored instead of dealt - a Flush later in the program lets it all out, and more. Not flushed this run, it is lost.",
  },
  {
    id: "flush",
    term: "Flush",
    // not a Glitch's "flush it out"
    pattern: /\bflush\b(?! it\b)/,
    text: "Control flow: deals everything the Buffers stored this run, plus a bonus.",
  },
  {
    id: "line-position",
    term: "Line position",
    pattern: /(?:first|last) to run|other queued lines?/,
    text: "Program mode: where its line stands counts - the first or the last line to run, and how many other lines are queued with it. The preview over a line shows what it comes out with there.",
  },
  {
    id: "program-ends",
    term: "Program ends",
    pattern: /program ends/,
    text: "Program mode: the lines after it don't run this turn - their cards go to the Graveyard unused.",
  },
  {
    id: "combo",
    term: "Combos",
    pattern: /\bcombos?\b/,
    text: "Program mode: card types run back to back pay out once per run - Fork, attack, Loop: Fork Bomb (+6 damage). Three attacks: Burst (+5). Block, attack, block: Sandwich (+6 block). Five lines through: Clean Run (+5).",
  },
  {
    id: "hot-path",
    term: "Hot Path",
    pattern: /\bhot path\b/,
    text: "An artifact: the card in its golden line runs as its upgraded version.",
  },
  {
    id: "interrupt",
    term: "Interrupt",
    pattern: /\binterrupt(?:s|ed)?\b/,
    text: "Enemy move: only your first lines run this turn - the cut ones go to the Graveyard unused. Put what matters first.",
  },
  {
    id: "refactor",
    term: "Refactor",
    pattern: /\brefactor(?:s|ed)?\b/,
    text: "Boss move: your program runs right to left this turn - Fork and Loop then steer the lines to their left.",
  },
  {
    id: "garbage-collector",
    term: "Garbage Collector",
    pattern: /\bgarbage collector\b/,
    text: "Enemy move: the last line of your program is thrown away before it runs and goes to the Graveyard unused. Don't save your best for last.",
  },
  {
    id: "race-condition",
    term: "Race Condition",
    pattern: /\brace condition\b/,
    text: "Enemy move: the first two lines of your program swap places - a Fork or If Wounded may end up behind what it was meant to steer.",
  },
  {
    id: "memory-leak",
    term: "Memory Leak",
    pattern: /\bmemory leak\b/,
    text: "Enemy move: the first line that runs stays locked for your next turn.",
  },
  {
    id: "malware",
    term: "Malware",
    pattern: /\bmalware\b|\binfect(?:s|ed)?\b/,
    text: "The infected side loses that much integrity at the end of each turn, then one stack fades. Ignores block.",
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
