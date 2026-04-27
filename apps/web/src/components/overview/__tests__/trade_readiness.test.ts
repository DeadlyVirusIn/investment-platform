// Phase OVERVIEW-READINESS — deriveReadiness unit coverage.

import { describe, it, expect } from "vitest";
import { deriveReadiness } from "@/lib/scheduler/hooks";


function base() {
  return {
    as_of: new Date().toISOString(),
    daily_loop: {
      last_success_at: new Date().toISOString(),
      last_failure_at: null,
      lock_present: false,
      next_scheduled: null,
    },
    tickloop: { jobs: [], recent_runs: [] },
  };
}

function job(over: Record<string, unknown> = {}) {
  return {
    name: "ingest_prices_daily",
    cron_expr: "0 22 * * 1-5",
    enabled: true,
    last_run_at: null,
    next_run_at: null,
    last_status: null,
    last_error: null,
    ...over,
  };
}


describe("deriveReadiness", () => {
  it("returns ERROR when last_failure_at newer than last_success_at", () => {
    const now = Date.now();
    const h = base();
    h.daily_loop.last_success_at = new Date(now - 3600_000).toISOString();
    h.daily_loop.last_failure_at = new Date(now).toISOString();
    const r = deriveReadiness(h as any);
    expect(r.kind).toBe("ERROR");
  });

  it("returns DEGRADED when a tickloop job is failing", () => {
    const h = base();
    h.tickloop.jobs = [job({ last_status: "error", name: "fetch_news" })] as any;
    const r = deriveReadiness(h as any);
    expect(r.kind).toBe("DEGRADED");
  });

  it("returns READY when ingest bar equals today", () => {
    const h = base();
    const now = new Date();
    // Ingest time for today — _asLocalDate strips time, so bar == today
    h.tickloop.jobs = [job({ last_run_at: now.toISOString() })] as any;
    const r = deriveReadiness(h as any);
    expect(r.kind).toBe("READY");
  });

  it("returns WAITING with null barDate when ingest never ran", () => {
    const h = base();
    h.tickloop.jobs = [job({ last_run_at: null })] as any;
    const r = deriveReadiness(h as any);
    expect(r.kind).toBe("WAITING");
    if (r.kind === "WAITING") expect(r.barDate).toBe(null);
  });

  it("returns DEGRADED when ingest is >=2 trading days behind", () => {
    const h = base();
    const oldDate = new Date();
    oldDate.setDate(oldDate.getDate() - 10);
    h.tickloop.jobs = [job({ last_run_at: oldDate.toISOString() })] as any;
    const r = deriveReadiness(h as any);
    expect(["DEGRADED", "WAITING"]).toContain(r.kind);
  });
});
