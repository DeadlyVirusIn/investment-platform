// UX-3D Phase A — view mode resolution.
//
// `?view=brief` / `?view=working`. URL is the single source of truth.
// NO localStorage persistence — bookmarkable, shareable, no surprise.
// Default: brief. Working is opt-in via URL.
//
// Phase A ships ONLY the parser. No UI mounts a different page based
// on this yet. Existing pages stay exactly where they are.

import type { ViewMode } from "./types";


export const DEFAULT_VIEW_MODE: ViewMode = "brief";


/** Parse the view mode from a URL search-string. Tolerant — anything
 *  unrecognised falls back to the default. NEVER throws. */
export function parseViewMode(search: string | null | undefined): ViewMode {
  if (!search) return DEFAULT_VIEW_MODE;
  let value: string | null = null;
  try {
    const params = new URLSearchParams(
      search.startsWith("?") ? search : "?" + search,
    );
    value = params.get("view");
  } catch {
    return DEFAULT_VIEW_MODE;
  }
  if (value === "brief" || value === "working") return value;
  return DEFAULT_VIEW_MODE;
}


/** React-side helper. Re-reads window.location on every call — cheap
 *  and side-effect-free, no subscription. Components that care about
 *  mode should re-render on route change naturally via React Router. */
export function getCurrentViewMode(): ViewMode {
  if (typeof window === "undefined") return DEFAULT_VIEW_MODE;
  return parseViewMode(window.location.search);
}
