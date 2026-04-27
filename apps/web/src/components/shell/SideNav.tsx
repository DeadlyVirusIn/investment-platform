import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";

const NAV = [
  { to: "/overview",   label: "Overview",    hot: "O" },
  { to: "/portfolio",  label: "Portfolio",   hot: "P" },
  { to: "/decisions",  label: "Decisions",   hot: "D" },
  { to: "/research",   label: "Alpha Lab",   hot: "A" },
  { to: "/ops",        label: "Ops",         hot: "S" },
  { to: "/options",    label: "Options",     hot: "X" },
];

export default function SideNav() {
  return (
    <aside className="w-[220px] shrink-0 bg-ink border-r border-b1
                      flex flex-col">
      <div className="px-5 py-6 border-b border-b1">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-accent flex items-center
                           justify-center text-[11px] font-bold text-white
                           tabular-nums">Q</div>
          <div>
            <div className="u-caption text-fg font-semibold">Quant Ops</div>
            <div className="u-caption-2 font-mono">v1.0.0</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 py-3 px-2">
        {NAV.map(n => (
          <NavLink key={n.to} to={n.to}
            className={({ isActive }) => cn(
              "group flex items-center justify-between px-3 py-2 rounded-md",
              "text-[13px] transition-colors duration-150",
              isActive
                ? "bg-accent-subtle text-fg font-medium"
                : "text-fg-2 hover:text-fg hover:bg-elev",
            )}>
            {({ isActive }) => (
              <>
                <span className="flex items-center gap-2.5">
                  <span className={cn(
                    "w-0.5 h-4 rounded-full",
                    isActive ? "bg-accent" : "bg-transparent",
                  )} />
                  {n.label}
                </span>
                <kbd className="text-[9px] uppercase tracking-wider
                                 text-fg-4 font-mono">
                  {n.hot}
                </kbd>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-b1 px-5 py-4">
        <div className="u-caption-2 mb-1">Environment</div>
        <div className="flex items-center gap-2 u-caption text-fg">
          <span className="u-dot u-dot-warning u-dot-pulse" />
          Paper Trading
        </div>
      </div>
    </aside>
  );
}
