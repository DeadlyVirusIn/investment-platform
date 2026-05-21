// Concept page — PR-5A Phase A.
// Stub variant: short definition + how-AI-uses + lessons-that-cover.
// Full content lands in PR-5B (replaces stub note + extends body).

import { Link, useParams } from "react-router-dom";

import TodayNav from "@/components/today/TodayNav";

import { getConcept, getLesson } from "@/lib/learn/curriculum";

import "../today/today.css";
import "@/styles/primitives.css";
import "./learn.css";


export default function ConceptPage() {
  const { slug } = useParams<{ slug: string }>();
  const concept = slug ? getConcept(slug) : undefined;

  if (!concept) {
    return (
      <div className="today-root">
        <TodayNav />
        <main className="learn-page">
          <Link to="/learn" className="learn-back">&larr; Back to Learn</Link>
          <h1 className="learn-term-title">{slug ?? "Concept"}</h1>
          <p className="today-empty">
            Full content for this concept arrives in the next release.
          </p>
        </main>
      </div>
    );
  }

  const lessons = concept.lessonSlugs
    .map(s => getLesson(s))
    .filter((l): l is NonNullable<typeof l> => l != null);

  return (
    <div className="today-root">
      <TodayNav />
      <main className="learn-page">

        <Link to="/learn" className="learn-back">&larr; Back to Learn</Link>

        <header className="mp-page-header">
          <div className="mp-eyebrow">
            Concept{concept.isStub && " · short definition · full page in next release"}
          </div>
          <h1 className="mp-page-title learn-term-title">{concept.label}</h1>
          <p className="mp-page-subtitle">{concept.shortDefinition}</p>
        </header>

        <h2 className="learn-term-subhead">How the engine uses it</h2>
        <p className="learn-term-body">{concept.howAIUses}</p>

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
