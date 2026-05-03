"""Layer 4 — strategy adapter. READ-ONLY around frozen production logic.

STRICT INVARIANT:
  Modules here may import from:
    - apps.api.src.data.features (production-flagged only, via registry)
    - apps.api.src.data.context.production
  Modules here MAY NOT import from:
    - apps.api.src.data.features.positioning (diagnostic)
    - apps.api.src.data.context.candidate, diagnostic

CI enforcement: grep for banned imports.
"""
