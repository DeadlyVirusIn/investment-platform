# Research Run Registry — Spec (Sprint 5)

Status: PROPOSAL — no migration generated, no code written. Approval-gated per
`CLAUDE.md` (Alembic migrations require explicit approval).
Source context: `docs/research/EXTERNAL_QUANT_AI_REVIEW_2026.md` §8 Pillar C,
§9 opportunity #5, §11 M3/M4. Style anchors: `apps/api/src/db/models.py`,
`infra/alembic/versions/104_accounts_m1.py`, `apps/api/src/api/admin_guard.py`.

## 1. Problem

The BP8–BP27B alpha investigation produced dozens of walk-forward and
calibration runs whose parameters, data windows, and verdicts live in chat
transcripts, memory files, and ad-hoc scripts. Nothing is reproducible from
the database. The registry is a **reproducible experiment ledger**: every
offline research run (walk-forward, Optuna study, calibration study,
backtest sweep) gets one durable, immutable row keyed by git SHA + data
hash + config hash + seed, so any result can be challenged, re-run, and
compared months later. It extends two existing disciplines:

- `proposal_hash` content-hashing on options trades (migration 093).
- Append-only, hash-keyed `reasoning_audit` envelopes
  (`apps/api/src/reasoning/audit.py` — "Append-only contract: no UPDATE
  path exposed").

Runs execute on the **dev machine only** (VM disk is a standing constraint;
review §5 "Resource exhaustion"). The DB row is small; artifacts stay on
dev disk.

## 2. SQL migration proposal

Next free revision slot is `109` (`108_app_user_role` is current head in
`infra/alembic/versions/`). **Do not generate the alembic file without
approval.** Proposed DDL:

```sql
-- 109_research_run.sql (PROPOSAL)

CREATE TABLE research_run (
    id                     VARCHAR(36)  PRIMARY KEY,           -- uuid4, house style (models.py _uuid)
    run_uid                VARCHAR(32)  NOT NULL,              -- public identifier, e.g. 'rr_20260709_a1b2c3'
    run_type               VARCHAR(32)  NOT NULL,
    name                   VARCHAR(256) NOT NULL,
    description            TEXT,
    status                 VARCHAR(16)  NOT NULL DEFAULT 'draft',
    git_sha                VARCHAR(64)  NOT NULL,              -- full sha of the code that ran
    model_version          VARCHAR(64),                        -- matches recommendation.model_version vocabulary
    feature_schema_version VARCHAR(64),
    data_start             DATE,
    data_end               DATE,
    data_hash              VARCHAR(64),                        -- sha256 over the input window manifest
    config_hash            VARCHAR(64)  NOT NULL,              -- sha256 over canonicalized parameters
    random_seed            BIGINT,
    split_method           VARCHAR(32),                        -- purged_walk_forward | expanding | kfold | none
    parameters             JSONB        NOT NULL DEFAULT '{}'::jsonb,
    metrics                JSONB        NOT NULL DEFAULT '{}'::jsonb,
    artifact_manifest      JSONB        NOT NULL DEFAULT '[]'::jsonb,
    parent_run_id          VARCHAR(36)  REFERENCES research_run(id) ON DELETE RESTRICT,
    promotion_status       VARCHAR(16)  NOT NULL DEFAULT 'none',
    promoted_at            TIMESTAMPTZ,
    started_at             TIMESTAMPTZ,
    completed_at           TIMESTAMPTZ,
    created_by             VARCHAR(64)  NOT NULL DEFAULT 'owner',  -- app_user.id or 'script:<name>'
    error_summary          TEXT,
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_research_run_uid UNIQUE (run_uid),
    CONSTRAINT ck_research_run_type CHECK (run_type IN
        ('walk_forward','optuna_study','optuna_trial','calibration',
         'backtest','feature_study','drift_study','other')),
    CONSTRAINT ck_research_run_status CHECK (status IN
        ('draft','running','completed','failed','aborted')),
    CONSTRAINT ck_research_run_promotion CHECK (promotion_status IN
        ('none','candidate','approved','rejected','promoted','rolled_back')),
    -- terminal rows must carry a completion timestamp; failures must explain themselves
    CONSTRAINT ck_research_run_completed CHECK
        (status NOT IN ('completed','failed','aborted') OR completed_at IS NOT NULL),
    CONSTRAINT ck_research_run_error CHECK
        (status <> 'failed' OR error_summary IS NOT NULL),
    -- promotion only ever granted to completed runs
    CONSTRAINT ck_research_run_promo_completed CHECK
        (promotion_status IN ('none','rejected') OR status = 'completed'),
    -- JSONB size caps (defense in depth; API enforces smaller limits first)
    CONSTRAINT ck_research_run_params_size   CHECK (pg_column_size(parameters)        <= 65536),
    CONSTRAINT ck_research_run_metrics_size  CHECK (pg_column_size(metrics)           <= 65536),
    CONSTRAINT ck_research_run_manifest_size CHECK (pg_column_size(artifact_manifest) <= 65536)
);

CREATE INDEX ix_research_run_type_created  ON research_run (run_type, created_at DESC);
CREATE INDEX ix_research_run_status        ON research_run (status);
CREATE INDEX ix_research_run_parent        ON research_run (parent_run_id);
CREATE INDEX ix_research_run_git_sha       ON research_run (git_sha);
CREATE INDEX ix_research_run_config_hash   ON research_run (config_hash);
CREATE INDEX ix_research_run_promoted      ON research_run (promotion_status)
    WHERE promotion_status <> 'none';

-- Companion table: promotion decisions are separate append-only rows, NOT
-- mutations of the run. This mirrors the proven options-canary pair
-- v2_promotion_snapshot / v2_promotion_approval (models.py:1393-1499):
-- decision + approver + rationale + content-hash binding, ON DELETE RESTRICT.
CREATE TABLE research_run_approval (
    id               VARCHAR(36) PRIMARY KEY,
    run_id           VARCHAR(36) NOT NULL REFERENCES research_run(id) ON DELETE RESTRICT,
    decision         VARCHAR(16) NOT NULL,   -- approve | reject | promote | rollback
    approver         VARCHAR(64) NOT NULL,   -- app_user.id of the owner (require_owner identity)
    rationale        TEXT        NOT NULL,
    run_content_hash VARCHAR(64) NOT NULL,   -- sha256 over the run row at decision time
    decided_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_research_run_approval_decision CHECK (decision IN
        ('approve','reject','promote','rollback'))
);
CREATE INDEX ix_research_run_approval_run ON research_run_approval (run_id, decided_at DESC);
```

Notes on deliberate choices:

- `run_uid` is the only identifier that appears in UI, logs, and artifact
  paths. The uuid PK stays internal (house style), `run_uid` is short and
  greppable.
- `parent_run_id` `ON DELETE RESTRICT`: children pin parents; the ledger
  never loses lineage silently.
- No `updated_at`: the row is either draft/running (narrow mutable window)
  or frozen. An audit of "what changed" is the approval table + metrics
  append log inside `metrics` (see §7).
- `data_hash` covers the *input manifest* (asset universe + bar count +
  min/max ts per table queried), not gigabytes of prices — cheap to
  recompute, sufficient to detect a shifted window.

## 3. ORM model proposal (SQLAlchemy 2, matching `models.py`)

```python
class ResearchRun(Base):
    """Sprint 5 — reproducible experiment ledger. Rows are frozen once
    terminal (see spec §7); promotion decisions live in
    research_run_approval, never as in-place edits."""

    __tablename__ = "research_run"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    run_uid: Mapped[str]     = mapped_column(String(32), nullable=False, unique=True)
    run_type: Mapped[str]    = mapped_column(String(32), nullable=False)
    name: Mapped[str]        = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str]      = mapped_column(String(16), nullable=False, default="draft")
    git_sha: Mapped[str]     = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None]          = mapped_column(String(64))
    feature_schema_version: Mapped[str | None] = mapped_column(String(64))
    data_start: Mapped[datetime.date | None]   = mapped_column(Date)
    data_end: Mapped[datetime.date | None]     = mapped_column(Date)
    data_hash: Mapped[str | None]   = mapped_column(String(64))
    config_hash: Mapped[str]        = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int | None] = mapped_column(BigInteger)
    split_method: Mapped[str | None] = mapped_column(String(32))
    parameters: Mapped[dict]        = mapped_column(JSON_COL, nullable=False, default=dict)
    metrics: Mapped[dict]           = mapped_column(JSON_COL, nullable=False, default=dict)
    artifact_manifest: Mapped[list] = mapped_column(JSON_COL, nullable=False, default=list)
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_run.id", ondelete="RESTRICT")
    )
    promotion_status: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    promoted_at: Mapped[datetime.datetime | None]  = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime.datetime | None]   = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str]         = mapped_column(String(64), nullable=False, default="owner")
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    parent: Mapped["ResearchRun | None"] = relationship(remote_side="ResearchRun.id")
    approvals: Mapped[list["ResearchRunApproval"]] = relationship(back_populates="run")

    __table_args__ = (
        Index("ix_research_run_type_created", "run_type", text("created_at DESC")),
        Index("ix_research_run_status", "status"),
        Index("ix_research_run_parent", "parent_run_id"),
        Index("ix_research_run_git_sha", "git_sha"),
        Index("ix_research_run_config_hash", "config_hash"),
        # CHECK constraints as in DDL — declared via CheckConstraint(...) here.
    )
```

`ResearchRunApproval` mirrors `V2PromotionApproval` (`models.py:1460`)
one-for-one with the field names from the DDL above.

## 4. API contract (owner-only)

All routes mount under `/api/admin/research-runs` with
`Depends(require_owner)` (`apps/api/src/api/admin_guard.py` — 404-not-403
posture, every access logged). No public or authenticated-user access in v1.

| Method & path | Purpose | Semantics |
|---|---|---|
| `POST /api/admin/research-runs` | Register a run | Body: run_type, name, description?, git_sha, model_version?, feature_schema_version?, data window, data_hash?, config_hash, random_seed?, split_method?, parameters, parent_run_id?. Server assigns `id`, `run_uid`, `status='draft'`, `created_at`. Rejects if an identical `(run_type, git_sha, config_hash, data_hash, random_seed)` completed run exists → 409 with the existing `run_uid` (dedupe, not double-count). Redaction filter applied to `parameters` (§10) before insert. |
| `PATCH /api/admin/research-runs/{run_uid}` | Lifecycle + metrics | Allowed transitions: `draft→running` (sets `started_at`), `running→completed|failed|aborted` (sets `completed_at`; `failed` requires `error_summary`). While `running`: `metrics` accepts **append-only merges** — new keys may be added, existing keys may NOT be overwritten (server compares and 409s on conflict); `artifact_manifest` entries may be appended. Any PATCH against a terminal run → 409 `run_frozen`, except manifest availability updates (§8) and nothing else. |
| `GET /api/admin/research-runs` | List | Filters: `run_type`, `status`, `promotion_status`, `git_sha`, `parent_run_uid`, date range; ordered `created_at DESC`; paginated (limit ≤ 200). Returns summary rows (no parameters/metrics bodies). |
| `GET /api/admin/research-runs/{run_uid}` | Detail | Full row + children summaries + approval history. |
| `GET /api/admin/research-runs/compare?a={uid}&b={uid}` | Diff two runs | Returns field-level diff: identity fields, parameter keys (added/removed/changed), metric deltas (numeric where both numeric), data-window overlap, git_sha same/different, seed same/different. Pure read; UI renders it. |
| `POST /api/admin/research-runs/{run_uid}/decision` | Promotion workflow | Body: decision (approve/reject/promote/rollback) + rationale (required, non-empty). Inserts `research_run_approval` row with `run_content_hash` computed server-side, then advances `promotion_status` per §9 state machine. Rationale-required mirrors `V2PromotionApproval.rationale NOT NULL`. |

Instrumented scripts (e.g. `scripts/` walk-forward runners) call the same
API from the dev machine with the owner session, or use a thin
`research_registry.py` helper writing through the ORM in-process — same
validation path either way (one write module, two entry points).

## 5. Owner-console UX sketch (`/v2/admin/research-runs`)

Follows the existing admin pages (`/v2/admin/jobs`, `/v2/admin/observability`).

- **List view**: table — run_uid · type badge · name · status chip
  (draft grey / running blue / completed green / failed red / aborted
  amber) · promotion chip · git_sha short · data window · created_at.
  Filter bar mirrors the GET filters. Optuna parents show a `+N trials`
  expander indented beneath them.
- **Detail view**: header (name, run_uid, status, promotion chip);
  identity card (git_sha with dirty/unknown warning if it matches a
  `build_provenance` flag, config_hash, data_hash, seed, split_method);
  parameters and metrics as collapsible key/value tables; artifact
  manifest table (path, sha256 short, size, kind, available ✓/✗);
  approval history timeline; "Compare with…" picker.
- **Diff view**: two columns, changed keys highlighted; metric deltas
  with sign coloring; top banner states whether the two runs are
  *comparable* (same run_type + overlapping data window) or not — the UI
  never implies a fair comparison it can't support.

Owner-only surface; no beginner-language requirement here (this is Layer-3
operator tooling by design — it must never leak into user-facing pages).

## 6. Example rows

```jsonc
// 1) Walk-forward run
{
  "run_uid": "rr_20260712_wf01", "run_type": "walk_forward",
  "name": "LGBM v3 purged WF, 900-name universe",
  "status": "completed", "git_sha": "5cdb099e…", "model_version": "lgbm_v3",
  "feature_schema_version": "fs_2026_07", "data_start": "2019-01-02",
  "data_end": "2026-06-30", "data_hash": "9f2c…", "config_hash": "41ab…",
  "random_seed": 1337, "split_method": "purged_walk_forward",
  "parameters": {"n_splits": 8, "embargo_days": 10, "cost_bps": 15,
                 "universe": "gap_backfill_900"},
  "metrics": {"oos_sharpe": 0.41, "oos_sharpe_vs_spy": -0.12,
              "hit_rate": 0.52, "n_trades": 1841,
              "verdict": "no_deployable_alpha"},
  "artifact_manifest": [{"path": "artifacts/research_runs/rr_20260712_wf01/folds.parquet",
                         "sha256": "c0ffee…", "bytes": 4194304,
                         "kind": "fold_results", "available": true}],
  "promotion_status": "rejected"
}

// 2) Optuna parent + one child trial
{ "run_uid": "rr_20260715_hp01", "run_type": "optuna_study",
  "name": "LGBM depth/leaves study", "status": "completed",
  "config_hash": "77de…", "parameters": {"n_trials": 50,
  "objective": "oos_sharpe", "sampler": "TPE", "storage": "postgres"},
  "metrics": {"best_trial_uid": "rr_20260715_hp01_t017", "best_value": 0.44} }
{ "run_uid": "rr_20260715_hp01_t017", "run_type": "optuna_trial",
  "parent_run_id": "<parent id>", "status": "completed",
  "config_hash": "8a91…", "random_seed": 1337,
  "parameters": {"max_depth": 6, "num_leaves": 41, "lr": 0.03},
  "metrics": {"oos_sharpe": 0.44, "trial_number": 17} }

// 3) Calibration study (feeds Trust Center "confidence calibration")
{ "run_uid": "rr_20260718_cal01", "run_type": "calibration",
  "name": "confidence_v2 reliability vs realized outcomes",
  "status": "completed", "split_method": "none",
  "data_start": "2026-01-01", "data_end": "2026-06-30",
  "parameters": {"method": "isotonic", "bands": 10,
                 "outcome_source": "recommendation_outcome.realized_30d_return"},
  "metrics": {"brier": 0.231, "n_resolved": 312,
              "band_coverage": {"60-70": 0.58, "70-80": 0.66},
              "verdict": "overconfident_above_70"},
  "promotion_status": "none" }
```

## 7. Immutability rules

1. **Terminal = frozen.** Once `status ∈ {completed, failed, aborted}`,
   every field is immutable except `artifact_manifest[*].available` /
   `verified_at` (availability is a fact about the disk, not about the
   experiment) and `promotion_status`/`promoted_at` — and those two move
   only through `POST …/decision`, which writes an approval row first.
2. **Retries are new runs.** A re-run of a failed/aborted experiment is a
   fresh row with `parent_run_id` pointing at the failure. Never reset a
   terminal run to `running`.
3. **Metrics are append-only until completion.** While `running`, keys can
   be added, never overwritten or deleted. A corrected metric is a new key
   (`oos_sharpe_corrected`) plus an explanatory key (`correction_note`),
   or a retry run. This is the `reasoning_audit` contract applied to
   experiments.
4. **No row deletion, ever** (see §8 for artifacts). `ON DELETE RESTRICT`
   on both FKs backs this at the DB layer.
5. Server computes `run_content_hash` (sha256 over a canonical JSON of the
   frozen row) at decision time; a later re-hash mismatch is a tamper
   signal surfaced in the admin console (same trick as
   `snapshot_content_hash` in `V2PromotionSnapshot`).

## 8. Artifact storage plan

- Location: dev machine `artifacts/research_runs/<run_uid>/` (gitignored;
  the repo's `.gitignore` already excludes bulk data dirs — verify entry
  before first run). Nothing on the VM: prod images never gain an
  artifacts mount.
- `artifact_manifest` is a JSONB array of
  `{path, sha256, bytes, kind, available, verified_at}`. The DB stores
  the **manifest only**, never file contents. `kind` vocabulary:
  `fold_results | reliability_curve | feature_importance | study_db |
  plot | report | other`.
- A `scripts/verify_research_artifacts.py` sweep recomputes sha256 for
  each manifest entry: missing file → `available=false`; hash mismatch →
  `available=false` + `verified_at` + a warning log (tampered ≠ deleted,
  but both mean "do not trust the artifact"). **The run row is never
  deleted or edited beyond that flag** — a run with lost artifacts is
  still a valid ledger entry; its metrics remain, its artifacts show ✗.
- Promoted runs' artifacts are copy-archived to
  `artifacts/promoted/<run_uid>/` at promotion time (promotion implies we
  may need the evidence years later).

## 9. Promotion approval workflow

Mirrors the options-canary governance chain
(`V2PromotionSnapshot.gates_json` + `V2PromotionApproval`, and the
operator-gated promote flow from the P6 canary work):

```
none ──(owner: candidate flagging via decision=approve)──▶ approved
none ──(decision=reject)──────────────────────────────────▶ rejected
approved ──(decision=promote, after gates)────────────────▶ promoted  (sets promoted_at)
promoted ──(decision=rollback, rationale required)────────▶ rolled_back
rejected / rolled_back ── terminal (a new attempt = a new run)
```

(`candidate` is the transient marking an owner applies in the UI before
recording the approve decision; it is stored so the console can show a
"pending decision" queue.)

Gates checked server-side before `promote` is accepted — all must hold:

1. `status = 'completed'` and `promotion_status = 'approved'`.
2. `git_sha` known (not `unknown`, not a `dirty_build` — cross-checked
   against `apps/api/src/build_provenance.py` semantics) and reachable on
   `origin` (ops step, recorded in rationale).
3. `data_hash`, `config_hash`, `random_seed` all non-null — an
   unreproducible run cannot be promoted, period.
4. An `approve` decision row exists from the owner with non-empty
   rationale, and its `run_content_hash` still matches the row.
5. Out-of-sample metrics present (`metrics` contains the keys declared
   required for its `run_type` in a small server-side table of gate
   specs) — no promotion on in-sample numbers.

"Promoted" here means *the config/model version is cleared to be wired
into the recommendation pipeline via the normal deploy process* — the
registry records the decision; it does not itself change engine behavior
(deploys remain HARD-STOP gated per global policy).

## 10. Privacy & security analysis

- **Access**: owner-only via `require_owner`; 404 posture hides existence.
  No anonymous, no authenticated-non-owner path. Every access logged
  (guard already does this).
- **Secrets in parameters — redaction list**: before insert, drop/mask any
  key matching (case-insensitive substring):
  `key, token, secret, password, passwd, credential, api_key, apikey,
  fernet, dsn, database_url, connection, cookie, session, bearer,
  authorization, private`. Values matching URL-with-userinfo
  (`scheme://user:pass@`) or high-entropy 32+ char base64/hex are masked
  to `"[redacted]"` + a `redactions: [key…]` note appended. This is the
  QuantDinger `_SECRET_KEYS` response-redaction pattern (review §5)
  applied at **write** time — redact before persist, not at render.
- **Size caps**: API rejects `parameters`/`metrics` > 32 KiB and
  `artifact_manifest` > 200 entries (413); DB CHECKs at 64 KiB are the
  backstop. Prevents accidental "dump the dataframe into metrics".
- **No code execution**: the registry stores *descriptions* of runs.
  It never stores or executes scripts (review §5: in-process exec is
  categorically rejected).
- **Injection surface**: all values parameterized (house style uses bound
  params everywhere, e.g. `apps/api/src/api/feedback.py`); `run_uid` is
  server-generated, never client-supplied.
- **PII**: none by construction — runs describe market-data experiments.
  `created_by` holds the owner's user id, not email.

## 11. Retention policy

- `research_run` and `research_run_approval` rows: **retained
  indefinitely** — the ledger is the product of this sprint; deleting
  rows would recreate the BP8–BP27B amnesia problem.
- Artifacts (dev disk): promoted runs — keep forever (archived copy);
  completed non-promoted — keep ≥ 365 days, then owner may GC files
  (flag flips to `available=false`, row untouched); failed/aborted —
  artifacts GC-able after 90 days.
- Optuna child-trial rows are exempt from artifact retention minimums
  (parents carry the study artifact); their DB rows still persist.
- Review the policy when the table passes ~50k rows (at expected volume,
  years away; a row is ~2–10 KB).

## 12. Rollback plan

- **Schema**: additive migration; downgrade = `DROP TABLE
  research_run_approval; DROP TABLE research_run;` — no existing table is
  touched, no data backfill exists, so downgrade is clean. `make
  db-backup` before upgrade per repo policy; test upgrade+downgrade
  against an ephemeral `pg-11v-test` container first (the MP1S/MP1A
  precedent).
- **API**: router mounted behind a `RESEARCH_REGISTRY_ENABLED: bool =
  False` settings flag (matching the fail-closed flag style of
  `RESEARCH_RO_ENABLED` in `apps/api/src/config/__init__.py`); rollback =
  flip flag, endpoints vanish, table stays.
- **UI**: admin page unlinked from SideNav; the guard makes it 404 anyway.
- **Data**: if the table must be abandoned, export
  `COPY research_run TO …csv` first — ledger data is the asset.

## 13. Test plan (summary)

- Unit: redaction filter (each pattern + nested keys), run_uid generation,
  content-hash canonicalization stability, append-only metrics merge
  (conflict → 409), state-machine transitions (valid + every invalid pair).
- Integration (pg): migration up/down; CHECK constraints (each enum, size
  caps via oversized payload, terminal-without-completed_at rejected);
  frozen-row PATCH rejected; decision flow end-to-end
  (approve→promote→rollback) with approval rows and content-hash binding;
  duplicate-run 409 dedupe; RESTRICT on parent delete.
- Guard: anonymous and non-owner → 404 on every route (extend
  `make test-auth` surface — admin routes are trust-critical).

## NON-GOALS

- Not an MLflow replacement or a generic tracking server; no UI charting
  of training curves (revisit per review §9 "revisit after validation").
- Does not schedule, execute, or sandbox experiment code; it records runs
  that scripts perform on the dev machine.
- No VM/prod involvement: no artifacts on the VM, no worker jobs, no new
  services.
- No automatic promotion — every promotion is an explicit owner decision
  with rationale.
- No user-facing surface in this sprint (Trust Center consumes it later,
  read-only, Sprint 7).
- No storage of datasets or model binaries in Postgres — manifests only.
