// TodayNav — Layer-1 navigation for the calm-mentor shell.
// Three visible links + ThemeToggle. All operator surfaces (Ops,
// Agents, Alpha Lab, Signal Lab, Diagnostics) are deliberately NOT
// listed here — they are reachable by direct URL only and must not
// be visually advertised.
//
// "Ideas" link removed (Phase A note): not part of approved ArthOS
// information architecture (Briefing / Learn / Portfolio / Journal /
// Track Record). Components TodaysIdeas + IdeaCard remain in tree
// for future reuse.

import { Link, useLocation } from "react-router-dom";

import { useTheme } from "@/lib/ui/theme";


const LAYER1_LINKS: ReadonlyArray<{ to: string; label: string }> = [
  { to: "/today",            label: "Today" },
  { to: "/today/portfolio",  label: "Portfolio" },
  { to: "/learn",            label: "Learn" },
];


export default function TodayNav() {
  const location = useLocation();
  const isActive = (path: string) => {
    if (path === "/today") {
      return location.pathname === "/today" || location.pathname === "/today/";
    }
    return location.pathname === path
      || location.pathname.startsWith(path + "/");
  };

  return (
    <nav className="today-nav" aria-label="Primary">
      <Link to="/today" className="today-nav-brand-row" aria-label="ArthOS home">
        <span className="today-nav-brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
            <path d="M19 14l.75 2.25L22 17l-2.25.75L19 20l-.75-2.25L16 17l2.25-.75L19 14z" />
          </svg>
        </span>
        <span className="today-nav-brand-name">ArthOS</span>
      </Link>
      <ul className="today-nav-links">
        {LAYER1_LINKS.map((l) => (
          <li key={l.to}>
            <Link
              to={l.to}
              className="today-nav-link"
              data-active={isActive(l.to) ? "true" : undefined}
            >
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
      <TodayThemeToggle />
    </nav>
  );
}


// Calm editorial theme toggle — fits the today-nav rhythm. Reuses the
// shared useTheme hook so the calm shell stays synchronized with the
// rest of the app's data-theme on <html>.
function TodayThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next: "dark" | "light" = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className="today-nav-theme-toggle"
      role="switch"
      aria-checked={theme === "light"}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
    >
      {theme === "dark" ? "light" : "dark"}
    </button>
  );
}
