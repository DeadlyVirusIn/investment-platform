"""Source-specific adapters.

Each adapter is a pure function (records → records) that pre-processes
feed-specific quirks BEFORE core ingestion:

  - attach explicit source_timezone to naive timestamps
  - attach explicit value_unit to numeric fields
  - synthesize external_id when feed omits it

Adapters do NOT touch normalized tables. They produce the dict-records
shape that the core ingestion jobs (ingest_earnings / ingest_shares /
ingest_consensus) consume. Keep adapters small, explicit, and testable.
"""
