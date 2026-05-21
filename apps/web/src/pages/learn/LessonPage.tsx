// Lesson page — PR-5A Phase A.
// Opening line · body (paragraph/subhead/liveData) · reflection prompt
// · next-lesson + back-to-brief CTAs. Records lastLessonSlug in
// localStorage for the Learn home "Where you are" hook.

import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";

import TodayNav from "@/components/today/TodayNav";

import {
  getLesson, getPath, getNextLesson,
} from "@/lib/learn/curriculum";

import "../today/today.css";
import "@/styles/primitives.css";
import "./learn.css";


export default function LessonPage() {
  const { slug } = useParams<{ slug: string }>();
  const lesson = slug ? getLesson(slug) : undefined;
  const path = lesson ? getPath(lesson.pathSlug) : undefined;
  const next = lesson ? getNextLesson(lesson.slug) : undefined;

  useEffect(() => {
    if (!lesson) return;
    try {
      window.localStorage.setItem("arthos.learn.lastLesson", lesson.slug);
    } catch { /* ignore */ }
  }, [lesson]);

  if (!lesson || !path) {
    return (
      <div className="today-root">
        <TodayNav />
        <main className="learn-page">
          <Link to="/learn" className="learn-back">&larr; Back to Learn</Link>
          <p className="today-empty">This lesson could not be found.</p>
        </main>
      </div>
    );
  }

  return (
    <div className="today-root">
      <TodayNav />
      <main className="learn-page">

        <Link to={`/learn/path/${path.slug}`} className="learn-back">
          &larr; Back to {path.title}
        </Link>

        <header className="mp-page-header">
          <div className="mp-meta">
            {lesson.minutes} min read · Lesson {lesson.order} · {path.tierLabel}
          </div>
          <h1 className="mp-page-title learn-lesson-title" style={{ marginTop: 12 }}>
            {lesson.title}
          </h1>
        </header>

        <p className="learn-lesson-opening">{lesson.openingLine}</p>

        {lesson.body.map((block, i) => {
          if (block.type === "paragraph") {
            return (
              <p key={i} className="learn-lesson-paragraph">
                {block.text}
              </p>
            );
          }
          if (block.type === "subhead") {
            return (
              <h2 key={i} className="learn-lesson-subhead">
                {block.text}
              </h2>
            );
          }
          if (block.type === "liveData") {
            return (
              <div key={i} className="learn-lesson-livedata">
                {block.description}
              </div>
            );
          }
          return null;
        })}

        <section className="learn-reflection">
          <p className="learn-reflection-label">A question for you</p>
          <p className="learn-reflection-prompt">{lesson.reflectionPrompt}</p>
        </section>

        <footer className="learn-lesson-footer">
          {next ? (
            <Link
              to={`/learn/lesson/${next.slug}`}
              className="learn-lesson-next"
            >
              Next lesson: {next.title} &rarr;
            </Link>
          ) : (
            <Link
              to={`/learn/path/${path.slug}`}
              className="learn-lesson-next"
            >
              Back to {path.title} &rarr;
            </Link>
          )}
          <Link to="/today" className="learn-lesson-secondary">
            Back to today's brief
          </Link>
        </footer>

      </main>
    </div>
  );
}
