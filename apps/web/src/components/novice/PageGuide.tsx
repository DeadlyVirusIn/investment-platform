// Phase NOVICE-UX (Commit 1) — standard page intro pattern.
//
// Layout per spec:
//   [Title — beginner phrasing]
//   [1-line subtitle: what this page tells you]
//   🟢 What you should look at first: <one sentence>
//   🛡️ Read-only — paper trading only.
//   [Optional: "Advanced details" disclosure handled separately]
//
// NEVER implies live trading or financial advice. Wraps no
// behavior; layout-only.

import { ReactNode } from "react";
import { cn } from "@/lib/cn";


export interface PageGuideProps {
  /** Plain-English title. Route paths stay unchanged; only the
   *  visible heading is novice-friendly. */
  title: string;
  /** One short sentence: what this page tells you. */
  subtitle?: string;
  /** One short sentence: what to look at first. Optional. */
  firstLook?: ReactNode;
  /** When false, suppress the read-only / paper-only footer line.
   *  Default true — every page that surfaces dollars or scores
   *  should keep it. */
  showReadOnlyFooter?: boolean;
  /** Optional eyebrow text above the title (e.g., "Read-only
   *  research"). */
  eyebrow?: string;
  /** Additional className passthrough. */
  className?: string;
}


export default function PageGuide({
  title,
  subtitle,
  firstLook,
  showReadOnlyFooter = true,
  eyebrow,
  className,
}: PageGuideProps) {
  return (
    <header
      data-test="novice-page-guide"
      className={cn("mb-4", className)}
    >
      {eyebrow && (
        <div
          data-test="novice-page-guide-eyebrow"
          className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1"
        >
          {eyebrow}
        </div>
      )}
      <h1
        data-test="novice-page-guide-title"
        className="u-title-lg"
      >
        {title}
      </h1>
      {subtitle && (
        <p
          data-test="novice-page-guide-subtitle"
          className="u-body mt-2 max-w-3xl text-zinc-300"
        >
          {subtitle}
        </p>
      )}
      {firstLook && (
        <p
          data-test="novice-page-guide-first-look"
          className="u-caption mt-2 max-w-3xl text-emerald-300/90"
        >
          <span aria-hidden="true">🟢 </span>
          <span className="text-zinc-400">First look: </span>
          <span className="text-zinc-200">{firstLook}</span>
        </p>
      )}
      {showReadOnlyFooter && (
        <p
          data-test="novice-page-guide-read-only"
          className="u-caption-2 mt-2 text-zinc-500"
        >
          <span aria-hidden="true">🛡️ </span>
          AI-generated research and paper-trading guidance · educational
          use only · nothing on this page places live orders · not financial advice.
        </p>
      )}
    </header>
  );
}
