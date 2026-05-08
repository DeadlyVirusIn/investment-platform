#!/usr/bin/env node
/*
 * UX-3D Phase A — anti-AI-theater + anti-causation lint.
 *
 * Scans:
 *   apps/web/src/lib/copilot/**\/*.ts
 *   apps/web/src/components/copilot/**\/*.tsx
 *
 * Rejects any presence of the banned tokens listed below in source
 * code. The lint runs before tsc + vite during `npm run build`.
 *
 * Failure exit code is non-zero so the build fails when banned
 * tokens leak in. Adding a new banned token is a one-line edit
 * to BANNED_TOKENS below.
 *
 * NOTE: matches are case-sensitive substring checks scoped to the
 * copilot directories only. The existing app pages are NOT scanned.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, sep } from "node:path";

const ROOT = new URL("../src", import.meta.url).pathname;
const COPILOT_DIRS = [
  join(ROOT, "lib", "copilot"),
  join(ROOT, "components", "copilot"),
];

// Banned tokens grouped by category. Each entry can be a literal
// substring (case-sensitive) or a /pattern/ regex (anchored as-is).
const BANNED_TOKENS = [
  // ---- AI theatre ------------------------------------------------
  "AI insight",
  "AI summary",
  "AI-generated",
  "Powered by AI",
  "powered by AI",
  "the AI noticed",
  "the AI thinks",
  "AI advisor",
  "machine learning",
  "model says",
  // ---- First-person engine / chatbot pretence -------------------
  "we think",
  "we believe",
  "I noticed",
  "I think",
  "let me know",
  // ---- Anthropomorphism -----------------------------------------
  "the market wants",
  "the market is saying",
  "strategies are watching", // demoted from earlier hero
  // ---- Predictive ------------------------------------------------
  "expected to",
  "likely to",
  "may continue",
  "could rise",
  "may break",
  // ---- Confidence theatre ---------------------------------------
  "high-confidence pick",
  "strong conviction",
  // ---- Hype / casino vocab --------------------------------------
  "🚀",
  "🔥",
  "📈",
  "hot pick",
  "trending",
  "watchlist banger",
  "spicy",
  // ---- Personalisation theatre ----------------------------------
  "personalised for you",
  "tailored to your profile",
  // ---- AI-rationale theatre (UX-4 lock 1) -----------------------
  // The only working-link copy is "See the working". Every other
  // phrasing implies hidden AI intelligence / authored rationale.
  "Read the full reasoning",
  "Read the reasoning",
  "Read the rationale",
  "View the analysis",
  "Open the rationale",
  "the full reasoning",
  // ---- Causation (in synthesis) ---------------------------------
  // These are scope-broad but copilot prose forbids them. Engineering
  // identifiers / SQL / comments may legitimately use them — that's
  // why scanning is restricted to copilot/ directories only.
  // Each prefixed with a space to reduce false positives in code.
  " because ",
  " driven by ",
  " due to ",
  " as a result ",
  " which means ",
];

let bad = 0;

function walk(dir) {
  const entries = readdirSync(dir);
  for (const e of entries) {
    const p = join(dir, e);
    const st = statSync(p);
    if (st.isDirectory()) {
      walk(p);
    } else if (
      st.isFile()
      && (p.endsWith(".ts") || p.endsWith(".tsx") || p.endsWith(".css"))
    ) {
      lint(p);
    }
  }
}

function lint(file) {
  // Skip the lint script itself (it lists the banned tokens).
  if (file.endsWith("lint-copilot-copy.mjs")) return;
  const text = readFileSync(file, "utf-8");
  for (const tok of BANNED_TOKENS) {
    if (text.includes(tok)) {
      // Allow tokens to live inside JSDoc / line comments that
      // explicitly document them as banned. Heuristic: a line that
      // also contains "banned" / "forbidden" / "BANNED" is allowed
      // to mention the token for documentation purposes.
      const lines = text.split(/\r?\n/);
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (!line.includes(tok)) continue;
        const lower = line.toLowerCase();
        if (
          lower.includes("banned")
          || lower.includes("forbidden")
          || lower.includes("// reject")
          || lower.includes("avoid")
          || lower.includes("never")
          || lower.includes("anti-")
        ) {
          continue; // doc reference — OK
        }
        const rel = file.replace(ROOT, "src");
        console.error(
          `lint-copilot-copy: ${rel}:${i + 1}: banned token ${JSON.stringify(tok)}`
          + `\n    ${line.trim()}`,
        );
        bad++;
      }
    }
  }
}

for (const d of COPILOT_DIRS) {
  try {
    walk(d);
  } catch (e) {
    // Directory doesn't exist yet — that's a Phase A reality.
    if (e && typeof e === "object" && "code" in e && e.code === "ENOENT") {
      continue;
    }
    throw e;
  }
}

if (bad > 0) {
  console.error(
    `\nlint-copilot-copy: ${bad} banned token reference(s) detected.`
    + ` Refusing to build.`,
  );
  process.exit(1);
}
process.exit(0);
