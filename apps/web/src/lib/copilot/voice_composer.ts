// UX-11 Phase 11A — AI voice composer (mixed regime + lint).
//
// Source of truth: docs/research/UX_11_INTERACTIVE_COPILOT.md
//   Section 5 (AI voice composer rules — mixed regime)
//
// Mixed regime:
//   - Hero: third-person ("The AI is...")
//   - Tile reads + drawer body: implicit voice
//   - Decision log: past-tense AI voice
//
// Composer rejects strings containing banned tokens. Throws
// VoiceLintError on violation.


export type VoiceSurface =
  | "hero"             // AIReadHero — third-person AI required
  | "tile-decision"    // tile decision sentence — implicit
  | "tile-bullbear"    // Bull/Bear inline clauses — implicit
  | "drawer-body"      // drawer thesis recap, sections — implicit
  | "decision-log";    // past-tense AI ("The AI promoted...")


export class VoiceLintError extends Error {
  constructor(message: string, public readonly text: string, public readonly surface: VoiceSurface) {
    super(`[UX-11 voice lint, surface=${surface}] ${message}`);
    this.name = "VoiceLintError";
  }
}


/** Tokens that are NEVER permitted regardless of surface. */
const UNIVERSALLY_BANNED_TOKENS = [
  "AI found",
  "AI-powered",
  "Powered by AI", // lint-copilot-allow-line — internal banlist literal
  "Ask me anything",
  "Here's what you should do",
  "Don't miss",
  "Before it's too late",
  "Guaranteed",
  "Based on my proprietary algorithm",
  "today's picks",
  "Hey there",
  // hype slang
  "crush",
  "moon",
  "explode",
  "rip",
  "discover",
  // emotion / persona
  "excited",
  "worried",
  "loves",
  "hates",
  "thinks",
  // imperatives
  "Trim now",
  "Buy now",
  "Sell now",
];


/** Lowercased ban list — matched as substring with word boundaries. */
const BANNED_LOWERCASE = UNIVERSALLY_BANNED_TOKENS.map(t => t.toLowerCase());


/** "AI" word may only appear in `hero` and `decision-log` surfaces. */
function checkAiWordRule(text: string, surface: VoiceSurface): void {
  if (surface === "hero" || surface === "decision-log") return;

  // Catches "AI", "the AI", "an AI" — but allow "AIRead" label compounds
  // by requiring AI as a standalone word.
  const aiWordPattern = /\b(?:the\s+|an\s+)?ai\b/i;
  if (aiWordPattern.test(text)) {
    throw new VoiceLintError(
      `surface '${surface}' must not contain the word 'AI' (mixed-voice regime); only hero and decision-log may attribute`,
      text, surface,
    );
  }
}


/** First-person pronouns banned outside the hero label context. */
function checkFirstPersonRule(text: string, surface: VoiceSurface): void {
  if (surface === "hero") return; // hero may use first-person if AI-attributed

  // Catches "I", "I'm", "we", "we're", "our", "us", "me", "my"
  const firstPersonPattern = /\b(?:I|I'm|I've|I'd|I'll|we|we're|we've|our|ours|us|me|my|mine)\b/;
  if (firstPersonPattern.test(text)) {
    throw new VoiceLintError(
      `surface '${surface}' contains first-person pronoun (banned outside hero label)`,
      text, surface,
    );
  }
}


/** Hero MUST start with "The AI is" or named stance verb. */
function checkHeroAttribution(text: string): void {
  if (!text.toLowerCase().startsWith("the ai")) {
    throw new VoiceLintError(
      `hero must begin with 'The AI' (third-person attribution required)`,
      text, "hero",
    );
  }
}


/** Decision log MUST start with "The AI" past-tense. */
function checkDecisionLogAttribution(text: string): void {
  if (!text.toLowerCase().startsWith("the ai")) {
    throw new VoiceLintError(
      `decision-log entry must begin with 'The AI' (past-tense AI subject required)`,
      text, "decision-log",
    );
  }
}


/** Length constraints per surface (master Section 3.4 + 4). */
function checkLength(text: string, surface: VoiceSurface): void {
  switch (surface) {
    case "hero": {
      if (text.length < 64 || text.length > 110) {
        throw new VoiceLintError(
          `hero must be 64-110 chars (got ${text.length})`,
          text, surface,
        );
      }
      // Single sentence — count sentence-end punctuation
      const sentenceEnds = (text.match(/[.!?](\s|$)/g) ?? []).length;
      if (sentenceEnds > 2) {
        throw new VoiceLintError(
          `hero should be 1-2 sentences (got ${sentenceEnds} sentence-ends)`,
          text, surface,
        );
      }
      break;
    }
    case "tile-decision": {
      if (text.length < 80 || text.length > 140) {
        throw new VoiceLintError(
          `tile decision must be 80-140 chars (got ${text.length})`,
          text, surface,
        );
      }
      break;
    }
    case "tile-bullbear": {
      if (text.length > 32) {
        throw new VoiceLintError(
          `tile bull/bear clause must be ≤ 32 chars (got ${text.length})`,
          text, surface,
        );
      }
      break;
    }
  }
}


/** Banned tokens (universal). */
function checkBannedTokens(text: string, surface: VoiceSurface): void {
  const lower = text.toLowerCase();
  for (const ban of BANNED_LOWERCASE) {
    // Word-boundary match
    const re = new RegExp(`\\b${ban.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    if (re.test(lower)) {
      throw new VoiceLintError(
        `contains banned token: '${ban}'`,
        text, surface,
      );
    }
  }
  // ALL-CAPS shouting (≥ 4 consecutive uppercase words)
  const allCapsPattern = /\b[A-Z]{2,}(\s+[A-Z]{2,}){3,}\b/;
  if (allCapsPattern.test(text)) {
    throw new VoiceLintError(
      `contains ALL-CAPS shouting (banned)`,
      text, surface,
    );
  }
}


/**
 * Validate text for the given voice surface. Throws VoiceLintError
 * on violation; returns text unchanged on success.
 */
export function validateVoice(text: string, surface: VoiceSurface): string {
  if (!text) {
    throw new VoiceLintError("text is empty", text ?? "", surface);
  }
  checkBannedTokens(text, surface);
  checkAiWordRule(text, surface);
  checkFirstPersonRule(text, surface);
  checkLength(text, surface);
  if (surface === "hero") checkHeroAttribution(text);
  if (surface === "decision-log") checkDecisionLogAttribution(text);
  return text;
}


/**
 * Compose an AIRead hero string from slot grammar.
 * Master Section 4.2: [STANCE_VERB] [QUALIFIER]. [CONSEQUENCE].
 */
export interface HeroSlotGrammar {
  stanceVerb:
    | "is becoming more selective"
    | "is leaning into"
    | "is reducing exposure to"
    | "is holding pattern on"
    | "sees no new entries warranted in";
  qualifier: string;     // "after this week's rally" / "as macro data softens"
  consequence: string;   // "Add only where earnings durability offsets valuation risk"
}

export function composeHeroFromGrammar(g: HeroSlotGrammar): string {
  const text = `The AI ${g.stanceVerb} ${g.qualifier}. ${g.consequence}`;
  return validateVoice(text, "hero");
}


/** Quiet-day fallback (master Section 1 L8 locked verbatim). */
export const QUIET_DAY_HERO = "Quiet day. Three theses unchanged. No new entries warranted.";
