"""Phase 11R - research-only paper fill paths.

Hard-isolated from the strict engine + auto-trader. Pure read of
existing price/feature data; writes append-only to the dedicated
`paper_research_fill` table. NEVER imports broker / live / execution
modules.
"""
