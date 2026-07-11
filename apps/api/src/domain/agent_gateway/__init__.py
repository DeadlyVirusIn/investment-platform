"""Agent Gateway v0 domain (Elite ArthOS Priority 7).

The REST API is the security boundary (spec §1). This package holds the
token model (`tokens`) and the single append-only audit trail (`audit`).
No module here imports execution / scoring / ML / paper / options code —
the gateway can read things, submit offline jobs, and write reviewable
drafts, and nothing more (spec §1 "paper-only is architectural").
"""
