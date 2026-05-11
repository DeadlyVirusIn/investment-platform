import { NavLink, useLocation } from "react-router-dom";
import { cn } from "@/lib/cn";
import { FLOW, SECTIONS, nextStep } from "@/lib/ui/page_flow";


export interface SideNavProps {
  // Phase 14f-A — invoked when user taps a nav item, so the parent
  // Shell can close the mobile drawer.
  onNavigate?: () => void;
}


export default function SideNav({ onNavigate }: SideNavProps = {}) {
  const { pathname } = useLocation();
  const nxt = nextStep(pathname);
  const nextTo = nxt?.to;

  return (
    <aside id="shell-sidenav"
           className="shell-sidenav w-[220px] shrink-0 bg-ink border-r border-b1
                      flex flex-col">
      <div className="px-5 py-6 border-b border-b1">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-accent flex items-center
                           justify-center text-[11px] font-bold text-white
                           tabular-nums">Q</div>
          <div>
            <div className="u-caption text-fg font-semibold">AI Investing OS</div>
            <div className="u-caption-2 font-mono">v1.0.0</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 py-3 px-2 overflow-y-auto">
        {SECTIONS.map(sec => {
          const items = FLOW.filter(f => f.section === sec.key);
          if (items.length === 0) return null;
          return (
            <div key={sec.key} className="mb-3">
              <div className="px-3 mt-2 mb-1 text-[10px] font-semibold
                              tracking-[0.16em] text-fg-4">
                {sec.label}
              </div>
              {items.map(n => (
                <NavLink key={n.to} to={n.to}
                  onClick={() => onNavigate?.()}
                  className={({ isActive }) => cn(
                    "group flex items-center justify-between px-3 py-1.5 rounded-md",
                    "text-[13px] transition-colors duration-150",
                    isActive
                      ? "bg-accent-subtle text-fg font-medium"
                      : nextTo === n.to
                        ? "text-fg hover:bg-elev"
                        : "text-fg-2 hover:text-fg hover:bg-elev",
                  )}>
                  {({ isActive }) => (
                    <>
                      <span className="flex items-center gap-2.5">
                        <span className={cn(
                          "w-0.5 h-4 rounded-full",
                          isActive
                            ? "bg-accent"
                            : nextTo === n.to
                              ? "bg-accent/40"
                              : "bg-transparent",
                        )} />
                        {n.label}
                        {nextTo === n.to && !isActive && (
                          <span className="text-[9px] uppercase tracking-wider
                                           text-accent/80 font-mono ml-1">
                            next
                          </span>
                        )}
                      </span>
                      <kbd className="text-[9px] uppercase tracking-wider
                                       text-fg-4 font-mono">
                        {n.hot}
                      </kbd>
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          );
        })}
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
