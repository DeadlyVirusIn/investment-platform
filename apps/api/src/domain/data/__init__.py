"""Phase 9 — event-data infrastructure.

Point-in-time correct storage + lookup for earnings events, shares
outstanding history, and consensus/actual EPS + revenue. Pure domain
layer; storage and ingestion are separable concerns.

Submodules:
  - time.py        — EventTime enum + tradable_date derivation (pure)
  - event_record.py— canonical EventRecord dataclass
  - earnings/      — EarningsEvent + EarningsRepo protocol + InMemory impl
  - shares/        — SharesOutstandingRecord + repo
  - consensus/     — ConsensusRecord + repo (handles consensus + actual)
  - pit_lookup.py  — PITDataContext: the public query API

Design invariants:
  1. Point-in-time > completeness
  2. Explicit > implicit (every lookup takes an as_of cutoff)
  3. Fail fast on missing / ambiguous data (no silent fill)
  4. Deterministic joins only (no "closest match" fuzziness)
  5. Separation of raw vs cleaned (source + raw_payload preserved)
"""
