// Learn home — PR-5A Phase A.
// Identity sentence + Where you are + Featured term + Path index +
// Glossary entry. No This-Week's-Concept (PR-5C), no Reflection link
// (PR-5C). The page degrades gracefully: first-time visitors see a
// "Start here" row; returning visitors see continuation.
//
// All copy is observational and passes the Tier-A 30-phrase lint.

import { Link } from "react-router-dom";

import TodayNav from "@/components/today/TodayNav";

import {
  PATHS, TERMS, getLesson, getPath, getPathsByTier,
} from "@/lib/learn/curriculum";

import "../today/today.css";
import "@/styles/primitives.css";
import "./learn.css";


// Local progress shim. PR-5C upgrades to localStorage adapter; for
// Phase A this returns no progress so the page always shows
// "Start here". Real progress wiring lands in PR-5C.
function getProgress(): { lastLessonSlug: string | null } {
  if (typeof window === "undefined") return { lastLessonSlug: null };
  try {
    const raw = window.localStorage.getItem("arthos.learn.lastLesson");
    return { lastLessonSlug: raw && raw.length > 0 ? raw : null };
  } catch {
    return { lastLessonSlug: null };
  }
}


function FeaturedTerm() {
  // Featured term is deterministic per UTC day. Phase A: pick first
  // term in the catalog (Drawdown). PR-5C will rotate.
  const term = TERMS[0];
  if (!term) return null;
  return (
    <Link to={`/learn/term/${term.slug}`} className="learn-featured-term">
      <h3 className="learn-featured-term-name">{term.term}</h3>
      <p className="learn-featured-term-def">{term.definition}</p>
      <span className="learn-featured-term-cta">Read full entry &rarr;</span>
    </Link>
  );
}


function WhereYouAre() {
  const progress = getProgress();
  const lesson = progress.lastLessonSlug ? getLesson(progress.lastLessonSlug) : null;
  const path = lesson ? getPath(lesson.pathSlug) : null;

  if (lesson && path) {
    return (
      <div>
        <p className="learn-where">
          <strong>{path.title}</strong>
          {" · "}
          <span className="learn-where-meta">Lesson {lesson.order}</span>
          <Link to={`/learn/lesson/${lesson.slug}`} className="learn-where-cta">
            Continue &rarr;
          </Link>
        </p>
      </div>
    );
  }

  // First-time visitor — recommend the first foundational path
  const startPath = PATHS.find(p => p.slug === "investing-basics") ?? PATHS[0];
  return (
    <div>
      <p className="learn-where">
        <strong>{startPath.title}</strong>
        {" · "}
        <span className="learn-where-meta">
          {startPath.lessonSlugs.length} lesson
          {startPath.lessonSlugs.length === 1 ? "" : "s"}
          {" · "}{startPath.totalMinutes} min
        </span>
        <Link to={`/learn/path/${startPath.slug}`} className="learn-where-cta">
          Begin &rarr;
        </Link>
      </p>
    </div>
  );
}


function PathListGroup({ tier, label }: { tier: 0 | 1 | 2 | 3; label: string }) {
  const paths = getPathsByTier(tier);
  if (paths.length === 0) return null;
  return (
    <div className="learn-path-group">
      <p className="learn-path-group-label">{label}</p>
      <ul className="learn-path-list">
        {paths.map(p => {
          const hasLessons = p.lessonSlugs.length > 0;
          const state = hasLessons ? "empty" : "coming";
          const meta = hasLessons
            ? `${p.lessonSlugs.length} lesson${p.lessonSlugs.length === 1 ? "" : "s"} · ${p.totalMinutes} min`
            : "Coming next release";
          return (
            <li className="learn-path-row" key={p.slug}>
              <span className="learn-path-mark" data-state={state} />
              {hasLessons ? (
                <Link to={`/learn/path/${p.slug}`} style={{ color: "inherit" }}>
                  <span className="learn-path-name">{p.title}</span>
                </Link>
              ) : (
                <span className="learn-path-name" data-coming="true">
                  {p.title}
                </span>
              )}
              <span className="learn-path-meta">{meta}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}


export default function LearnHomePage() {
  return (
    <div className="today-root">
      <TodayNav />
      <main className="learn-page">

        <header className="mp-page-header">
          <div className="mp-eyebrow">Learn</div>
          <h1 className="mp-page-title learn-page-title">
            Learn how to invest by watching an AI invest, explain itself, and admit mistakes.
          </h1>
          <p className="mp-page-subtitle">
            Foundational paths first. A few minutes most days, one short
            reflection on weekends.
          </p>
        </header>

        <section className="learn-section">
          <p className="mp-section-label">Where you are</p>
          <WhereYouAre />
        </section>

        <section className="learn-section">
          <p className="mp-section-label">Featured term</p>
          <FeaturedTerm />
        </section>

        <section className="learn-section">
          <p className="mp-section-label">Learning paths</p>
          <PathListGroup tier={0} label="Foundations" />
          <PathListGroup tier={1} label="Foundations · product" />
          <PathListGroup tier={2} label="Risk and reflection" />
          <PathListGroup tier={3} label="Skill" />
        </section>

        <section className="learn-section">
          <p className="mp-section-label">Glossary</p>
          <p className="learn-where">
            Definitions across investing, the engine, and your portfolio.
            {" "}
            <Link to="/learn/glossary" className="learn-glossary-cta">
              Browse glossary &rarr;
            </Link>
          </p>
        </section>

      </main>
    </div>
  );
}
