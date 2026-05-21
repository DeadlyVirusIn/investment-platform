// Learn Path landing — PR-5A Phase A.
// Synopsis · lesson list · outcome · related concepts.

import { Link, useParams } from "react-router-dom";

import TodayNav from "@/components/today/TodayNav";

import {
  getPath, getLessonsForPath, getConcept,
} from "@/lib/learn/curriculum";

import "../today/today.css";
import "@/styles/primitives.css";
import "./learn.css";


export default function LearnPathPage() {
  const { slug } = useParams<{ slug: string }>();
  const path = slug ? getPath(slug) : undefined;

  if (!path) {
    return (
      <div className="today-root">
        <TodayNav />
        <main className="learn-page">
          <Link to="/learn" className="learn-back">&larr; Back to Learn</Link>
          <p className="today-empty">This path could not be found.</p>
        </main>
      </div>
    );
  }

  const lessons = getLessonsForPath(path.slug);
  const concepts = path.relatedConcepts
    .map(s => getConcept(s))
    .filter((c): c is NonNullable<typeof c> => c != null);

  return (
    <div className="today-root">
      <TodayNav />
      <main className="learn-page">

        <Link to="/learn" className="learn-back">&larr; Back to Learn</Link>

        <header className="mp-page-header">
          <div className="mp-eyebrow">
            Learning path · {path.tierLabel}
          </div>
          <h1 className="mp-page-title learn-path-title">{path.title}</h1>
          <p className="mp-page-subtitle">{path.synopsis}</p>
          <p className="mp-meta" style={{ marginTop: 16 }}>
            {path.lessonSlugs.length} lesson
            {path.lessonSlugs.length === 1 ? "" : "s"} · {path.totalMinutes} min read
          </p>
        </header>

        <section className="learn-section">
          <p className="mp-section-label">Lessons</p>
          {lessons.length === 0 ? (
            <p className="today-empty">
              Lessons for this path arrive in the next release.
            </p>
          ) : (
            <ul className="learn-lesson-list">
              {lessons.map(l => (
                <li className="learn-lesson-row" key={l.slug}>
                  <span className="learn-lesson-num">{l.order}.</span>
                  <Link to={`/learn/lesson/${l.slug}`}>{l.title}</Link>
                  <span className="learn-lesson-min">{l.minutes} min</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="learn-section">
          <p className="mp-section-label">After this path</p>
          <p className="learn-path-outcome">{path.outcome}</p>
        </section>

        {concepts.length > 0 && (
          <section className="learn-section">
            <p className="mp-section-label">Related concepts</p>
            <div className="learn-concept-chips">
              {concepts.map(c => (
                <Link
                  key={c.slug}
                  to={`/learn/concept/${c.slug}`}
                  className="learn-concept-chip"
                >
                  {c.label}
                </Link>
              ))}
            </div>
          </section>
        )}

      </main>
    </div>
  );
}
