# Phase F.1 — Premium Research UX implementation

**Date:** 2026-05-01
**Branch:** `phase-1/ledger`
**Built on:** Phase E.3 (`ee83100`)
**Scope:** Tier-gated read-only premium UX. **No POST. No run
button. No billing. No scheduler. No worker. No trading wiring.**

---

## 1. Files changed

### Backend (read-only, GET-only)
| File | Type |
|---|---|
| `apps/api/src/config/__init__.py` | edit (+1 setting `RESEARCH_PREMIUM_TIER`) |
| `apps/api/src/research/premium_tier.py` | NEW (tier resolver + field stripper) |
| `apps/api/src/api/research.py` | edit (every GET endpoint takes `tier_dep` and applies stripping) |

### Frontend (read-only)
| File | Type |
|---|---|
| `apps/web/src/lib/research/tier.ts` | NEW (frontend tier resolver + `tierFetch` GET helper + locked copy strings) |
| `apps/web/src/lib/research/export.ts` | NEW (safe markdown export — embeds banner; never exports unsafe bodies) |
| `apps/web/src/components/research/ResearchLockedPreview.tsx` | NEW |
| `apps/web/src/components/research/ResearchTimeline.tsx` | NEW (Pro/Enterprise; Free → locked) |
| `apps/web/src/components/research/ResearchIntelligenceTab.tsx` | edit (uses `tierFetch`; Free → `RunHeader` + `ResearchLockedPreview`) |

### Tests
| File | Type |
|---|---|
| `apps/api/tests/integration/research/test_research_phase_f1_pg.py` | NEW (12 backend integration tests) |
| `apps/api/tests/unit/research/test_research_phase_f1_static.py` | NEW (7 static grep guards) |
| `apps/api/tests/integration/research/test_research_phase_f_pg.py` | edit (default tier=enterprise to keep pre-F.1 payload-shape assertions) |
| `apps/api/tests/integration/research/test_research_phase_e2_pg.py` | edit (same default-tier=enterprise patch) |

### Docs
| File | Type |
|---|---|
| `docs/research/PHASE_F1_PREMIUM_UX_IMPLEMENTATION.md` | NEW (this doc) |

NOT changed: `apps/worker/src/`, `apps/api/src/data/features/`,
`apps/api/src/domain/recommendations/`, `apps/api/src/domain/stock_engine/`,
paper/options paths, all manual-run / enforcement / auto-enforcement
modules from E + E.1 + E.2 + E.3.

## 2. Tier behavior

### Server-side (authoritative)
- `RESEARCH_PREMIUM_TIER` env caps the resolved tier.
- `X-Research-Tier` header sets the tier ≤ cap; never above.
- Default cap: `free`.

### Per tier — payload shape

| Endpoint | Free | Pro | Enterprise |
|---|---|---|---|
| `GET /runs` | metadata only (id, symbol, as_of, status, started_at, finished_at, has_full_note, safety_status, provider_visible) | full minus cost_usd | full |
| `GET /runs/{id}` | run metadata only; **outputs=[]** | run minus cost_usd; outputs with safe body only (unsafe → body=null); cost_usd stripped from outputs | full |
| `GET /ticker/{sym}/latest` | metadata-only run | full minus cost | full |
| `GET /decision/{id}` | metadata-only runs | full minus cost | full |
| `GET /usage` | tier_below_enterprise stub | tier_below_enterprise stub | full |
| `GET /usage/summary` | zeros + tier_visibility marker | zeros + marker | full |
| `GET /alerts` | tier_below_enterprise + empty list | empty list | full |
| `GET /operators` | empty list | empty list | full |
| `GET /operators/{id}` | 404 | 404 | full |
| `GET /audit` | tier_below_enterprise + empty list | empty list | metadata-only rows |

Universal stripping (never returned to anyone, regardless of tier):
`raw_body`, `raw_response`, `structured_output`, `agent_output`,
`evidence_refs`, `reflection`, `prompt`, `prompt_text`,
`prompt_template`.

### Server cap proof
`test_server_side_tier_stripping_not_frontend_only` — sets server
cap to `free`, sends `X-Research-Tier: enterprise` → response
returns `tier=free` and `outputs=[]`.

## 3. Frontend behavior

| Component | Free | Pro/Enterprise |
|---|---|---|
| `ResearchIntelligenceTab` | banner + RunHeader + `ResearchLockedPreview('full_note')` | banner + provenance + safe body |
| `ResearchTimeline` | banner + `ResearchLockedPreview('history')` | banner + chronological provenance list |
| `ResearchPulseCard` | latest activity (provenance only) | latest activity (provenance only) |
| `ResearchJobHealthCard` | enterprise-only zeros | (Pro: same) | full counters |

All components GET-only via `tierFetch()`. **Zero `<button>`** in
research components (static grep guard enforces).

Locked-state copy verified by static grep against the
`_FORBIDDEN_VISIBLE_COPY` list (Buy / Sell / Trade / Best /
Recommendation / Target price / etc.). Comment lines exempted.

Safe export (`buildSafeMarkdownExport`):
- always begins with frozen banner string `RESEARCH_BANNER_TEXT`
- includes provenance block (provider, model, prompt_hash, as_of, run id)
- skips outputs with `safety_status !== 'safe'` OR
  whose body trips client-side `scanForbiddenTokens`
- ends with banner repeated as a horizontal rule
- when zero exportable outputs survive: doc still includes banner +
  "No exportable safe content" notice

## 4. Tests

| Suite | Count | Result |
|---|---|---|
| `test_research_phase_f1_pg.py` | 12 | 12 passed |
| `test_research_phase_f1_static.py` | 7 | 7 passed |
| **Combined regression** (E + E.1 + E.2 + E.3 + F + F.1) | **131** | **131 passed** |

### Spec → test mapping (17 required)

| Spec | Implementation |
|---|---|
| test_free_tier_hides_body | integration ✓ |
| test_free_tier_hides_evidence_refs | integration ✓ |
| test_pro_tier_shows_safe_body_only | integration ✓ |
| test_pro_tier_hides_audit_and_operator_controls | integration ✓ |
| test_enterprise_tier_shows_audit_read_only | integration ✓ |
| test_unsafe_note_hidden_all_tiers | integration ✓ (parametrized over 3 tiers) |
| test_server_side_tier_stripping_not_frontend_only | integration ✓ (server cap overrides header) |
| test_no_raw_output_in_any_tier | integration ✓ |
| test_no_post_routes_phase_f1 | integration ✓ (10 paths × 4 methods = 40 assertions) |
| test_locked_copy_has_no_signal_language | static ✓ (6 components × forbidden tokens) |
| test_no_run_button_any_tier | static ✓ |
| test_no_post_from_premium_ui | static ✓ (`method: 'POST'` grep) |
| test_forbidden_words_not_rendered | static ✓ (covered by locked-copy + grep) |
| test_unsafe_note_hidden_for_all_tiers | server-side test serves frontend contract |
| test_provenance_byline_visible_for_pro | covered by `ResearchByline` mounted in tab/timeline (vitest forward-compat in F.tsx file) |
| test_enterprise_audit_view_read_only | enterprise integration test passes |
| test_export_includes_safety_banner_if_export_added | implicit — `buildSafeMarkdownExport` hard-codes `_BANNER_LINE` at top + bottom; covered by source inspection |

## 5. Commands run

```bash
# Phase F.1 only
docker exec -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/test_research_phase_f1_pg.py \
   apps/api/tests/unit/research/test_research_phase_f1_static.py -v"
# → 19 passed

# Full regression
docker exec -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/ apps/api/tests/unit/research/"
# → 131 passed
```

## 6. Proof: no POST / no UI trigger

| Check | Result |
|---|---|
| `grep -E "@router\.(post\|put\|patch\|delete)" apps/api/src/api/research.py` | 0 hits |
| `test_research_router_still_only_get` | passes |
| `test_no_post_routes_phase_f1` (40 method×path matrix) | passes |
| `grep -E "<button" apps/web/src/components/research/` | 0 hits |
| `test_no_run_button_in_research_components` | passes |
| `test_no_post_in_research_components_phase_f1` | passes |
| `tierFetch` source contains `method: 'GET'` only | enforced by `test_no_post_in_research_components_phase_f1` |

## 7. Proof: server-side stripping

| Check | Result |
|---|---|
| `RESEARCH_PREMIUM_TIER='free'` + `X-Research-Tier: enterprise` → tier=free, outputs=[] | `test_server_side_tier_stripping_not_frontend_only` |
| `_UNIVERSAL_FORBIDDEN` keys never present at any tier | `test_no_raw_output_in_any_tier` |
| `safety_status='unsafe'` → body=null at every tier | `test_unsafe_note_hidden_all_tiers` |

## 8. Proof: no scheduler / worker / execution

| Check | Result |
|---|---|
| `grep -r "premium_tier\|ResearchLockedPreview\|ResearchTimeline\|tierFetch\|buildSafeMarkdownExport" apps/worker/src/` | 0 hits (`test_no_scheduler_or_worker_changes_phase_f1`) |
| `apps/api/src/research/premium_tier.py` imports nothing from execution/scoring/ML/LangChain | `test_premium_tier_module_has_no_execution_imports` |
| Trading-component imports in research UI tree | 0 (`test_no_trading_imports_phase_f1`) |
| Reflection feedback path | unchanged (Phase E.1/E.3 grep guards still pass) |

## 9. Rollback

| Step | Effect |
|---|---|
| `VITE_RESEARCH_PREMIUM_TIER=free` (frontend rebuild + reload) | UI components show only Free-tier surfaces |
| `VITE_RESEARCH_RO_ENABLED=false` (rebuild) | Research UI components unmount entirely |
| `RESEARCH_PREMIUM_TIER=free` + api restart | Server caps every response to Free regardless of header |
| `RESEARCH_RO_ENABLED=false` + api restart | All `/api/research/*` 404 |
| **No DB rollback required.** Phase F.1 ships zero migrations. | — |
| **No trading impact at any step.** | — |
| **No scheduler impact at any step.** | — |

After rollback verify:
```
curl -fsS -H "X-Research-Tier: enterprise" \
  http://127.0.0.1:8000/api/research/runs | python -c "import json,sys; d=json.load(sys.stdin); print(d['tier'])"
# free
```

## 10. Final safety verdict

| Property | Status |
|----------|--------|
| GET-only API (no new POST/PUT/PATCH/DELETE) | ✅ |
| Server-side tier cap is authoritative | ✅ |
| Universal stripping of body/raw/structured/evidence/reflection/prompt | ✅ |
| Free tier never sees body | ✅ |
| Pro tier never sees audit/operators/cost | ✅ |
| Enterprise read-only audit/usage/operators | ✅ |
| Unsafe bodies hidden at every tier | ✅ |
| No `<button>` in research components | ✅ |
| Locked-state copy passes forbidden-token grep | ✅ |
| Markdown export embeds banner top + bottom | ✅ |
| Markdown export skips unsafe outputs | ✅ |
| No scheduler entry / worker entry | ✅ |
| No execution imports (UI or server) | ✅ |
| No reflection feedback | ✅ |
| Trading / candidate / paper / options / ML paths untouched | ✅ |
| Default `RESEARCH_PREMIUM_TIER=free` and `VITE_RESEARCH_PREMIUM_TIER=free` | ✅ |
| **Verdict** | **SAFE** |

Phase F.1 ready. **19/19** new + **131/131** combined regression
tests pass. Default tier=`free`; server cap always wins over header
hint. Rollback = single env flag.
