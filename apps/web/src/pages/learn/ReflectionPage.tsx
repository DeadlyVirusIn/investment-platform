// Reflection page — PR-5A Phase A placeholder.
// Full reflection UX (4 questions, localStorage save) lands in PR-5C.
// Route exists in Phase A so the nav structure is complete.

import { Link } from "react-router-dom";

import TodayNav from "@/components/today/TodayNav";

import "../today/today.css";
import "@/styles/primitives.css";
import "./learn.css";


export default function ReflectionPage() {
  return (
    <div className="today-root">
      <TodayNav />
      <main className="learn-page">
        <Link to="/learn" className="learn-back">&larr; Back to Learn</Link>
        <h1 className="learn-page-title">Weekly reflection</h1>
        <p className="learn-reflection-placeholder">
          Weekly reflection arrives in the next release. It will ask
          four short questions every Saturday, save locally, and never
          leave your device.
        </p>
      </main>
    </div>
  );
}
