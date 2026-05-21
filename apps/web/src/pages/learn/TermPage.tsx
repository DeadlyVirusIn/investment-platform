// Term page — PR-5A Phase A.
// Definition · why-matters · how-AI-uses · related-terms · lessons.

import { Link, useParams } from "react-router-dom";

import TodayNav from "@/components/today/TodayNav";

import { getTerm, getLesson } from "@/lib/learn/curriculum";

import "../today/today.css";
import "@/styles/primitives.css";
import "./learn.css";


export default function TermPage() {
  const { slug } = useParams<{ slug: string }>();
  const term = slug ? getTerm(slug) : undefined;

  if (!term) {
    return (
      <div className="today-root">
        <TodayNav />
        <main className="learn-page">
          <Link to="/learn/glossary" className="learn-back">
            &larr; Back to Glossary
          </Link>
          <h1 className="learn-term-title">{slug ?? "Term"}</h1>
          <p className="today-empty">
            This term is not yet defined. The glossary fills in
            during the next release.
          </p>
        </main>
      </div>
    );
  }

  const lessons = term.lessonSlugs
    .map(s => getLesson(s))
    .filter((l): l is NonNullable<typeof l> => l != null);

  return (
    <div className="today-root">
      <TodayNav />
      <main className="learn-page">

        <Link to="/learn/glossary" className="learn-back">
          &larr; Back to Glossary
        </Link>

        <header className="mp-page-header">
          <div className="mp-eyebrow">Glossary · {term.category}</div>
          <h1 className="mp-page-title learn-term-title">{term.term}</h1>
          <p className="mp-page-subtitle">{term.definition}</p>
        </header>

        <h2 className="learn-term-subhead">Why it matters</h2>
        <p className="learn-term-body">{term.whyItMatters}</p>

        <h2 className="learn-term-subhead">How the engine uses it</h2>
        <p className="learn-term-body">{term.howAIUses}</p>

        {term.relatedTerms.length > 0 && (
          <>
            <h2 className="learn-term-subhead">Related terms</h2>
            <div className="learn-concept-chips">
              {term.relatedTerms.map(rt => (
                <Link
                  key={rt}
                  to={`/learn/term/${rt}`}
                  className="learn-concept-chip"
                >
                  {rt}
                </Link>
              ))}
            </div>
          </>
        )}

        {lessons.length > 0 && (
          <>
            <h2 className="learn-term-subhead">Lessons that cover this</h2>
            <ul className="learn-lesson-list" style={{ marginTop: "12px" }}>
              {lessons.map(l => (
                <li className="learn-lesson-row" key={l.slug}>
                  <span className="learn-lesson-num">·</span>
                  <Link to={`/learn/lesson/${l.slug}`}>{l.title}</Link>
                  <span className="learn-lesson-min">{l.minutes} min</span>
                </li>
              ))}
            </ul>
          </>
        )}

      </main>
    </div>
  );
}
