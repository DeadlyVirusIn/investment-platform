// Tiny hook: re-renders the parent every 60 seconds so relative-time
// strings ("14h ago", "8h ago") tick forward without manual refresh.
//
// Used by ActivityStream + ambient timestamp. Returns a number that
// changes on each tick — components can ignore the value and just
// rely on the re-render.

import { useEffect, useState } from "react";


export function useTickEverySecond(intervalMs: number = 60_000): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return tick;
}
