// UX-11 Phase 11C — drawer URL state hook.
//
// Source of truth: docs/research/UX_11_INTERACTIVE_COPILOT.md
//   Section 11 (URL state contract)
//
// Manages ?drawer=<TICKER> on top of existing search params.
// Browser back closes drawer before leaving page.

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";


export function useDrawerUrlState(): {
  openTicker: string | null;
  openDrawer: (ticker: string) => void;
  closeDrawer: () => void;
} {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();

  const readFromUrl = useCallback((): string | null => {
    const params = new URLSearchParams(search);
    return params.get("drawer");
  }, [search]);

  const [openTicker, setOpenTicker] = useState<string | null>(readFromUrl);

  useEffect(() => {
    setOpenTicker(readFromUrl());
  }, [readFromUrl]);

  const openDrawer = useCallback((ticker: string) => {
    const params = new URLSearchParams(search);
    params.set("drawer", ticker);
    // pushState so browser back closes the drawer first
    navigate({ pathname, search: `?${params.toString()}` }, { replace: false });
  }, [navigate, pathname, search]);

  const closeDrawer = useCallback(() => {
    const params = new URLSearchParams(search);
    params.delete("drawer");
    const next = params.toString();
    navigate(
      { pathname, search: next ? `?${next}` : "" },
      { replace: true },
    );
  }, [navigate, pathname, search]);

  return { openTicker, openDrawer, closeDrawer };
}
