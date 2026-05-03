"""Feature Registry loader + enforcement.

Reads config/feature_registry.yaml, validates, exposes guard functions.
Strategy layer MUST call require_production_feature() before using any
feature — violation raises NonProductionFeatureError.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

_VALID_STATUSES = {"production", "candidate", "diagnostic"}


@dataclass(frozen=True)
class FeatureEntry:
    name: str
    feature_version: str
    source: str
    availability_lag_days: int
    availability: str
    status: Literal["production", "candidate", "diagnostic"]
    contributes_to: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class ContextEntry:
    name: str
    logic_version: str
    status: Literal["production", "candidate", "diagnostic"]
    source_features: tuple[str, ...]
    logic_description: str
    logic_fingerprint: str


@dataclass(frozen=True)
class FeatureRegistry:
    version: str
    last_updated: str
    features: dict[str, FeatureEntry]
    contexts: dict[str, ContextEntry]
    decision_versions: dict[str, str]

    def get_feature_status(self, name: str) -> str:
        if name not in self.features:
            raise KeyError(f"feature not in registry: {name}")
        return self.features[name].status

    def is_production_feature(self, name: str) -> bool:
        return (name in self.features
                and self.features[name].status == "production")

    def require_production_feature(self, name: str) -> FeatureEntry:
        """Raise if feature is not approved for production strategy use."""
        if name not in self.features:
            raise NonProductionFeatureError(
                f"feature '{name}' not in registry"
            )
        entry = self.features[name]
        if entry.status != "production":
            raise NonProductionFeatureError(
                f"feature '{name}' is '{entry.status}' — strategy layer may "
                f"only use production-flagged features"
            )
        return entry

    def get_feature_version_lock(self, name: str) -> str:
        """Active feature version lock — strategy reads must use this version."""
        return self.features[name].feature_version

    def get_context_version_lock(self, name: str) -> str:
        return self.contexts[name].logic_version

    def require_production_context(self, name: str) -> ContextEntry:
        if name not in self.contexts:
            raise NonProductionFeatureError(
                f"context '{name}' not in registry"
            )
        ctx = self.contexts[name]
        if ctx.status != "production":
            raise NonProductionFeatureError(
                f"context '{name}' is '{ctx.status}' — strategy may only "
                f"use production-flagged contexts"
            )
        return ctx


class NonProductionFeatureError(RuntimeError):
    """Strategy attempted to use a non-production feature or context."""


def load_registry(
    path: Path | str = "config/feature_registry.yaml",
) -> FeatureRegistry:
    text = Path(path).read_text()
    raw = yaml.safe_load(text)

    features: dict[str, FeatureEntry] = {}
    for f in raw.get("features", []):
        status = f["status"]
        if status not in _VALID_STATUSES:
            raise ValueError(f"invalid status '{status}' for feature {f['name']}")
        features[f["name"]] = FeatureEntry(
            name=f["name"],
            feature_version=f["feature_version"],
            source=f["source"],
            availability_lag_days=int(f.get("availability_lag_days", 0)),
            availability=f.get("availability", ""),
            status=status,
            contributes_to=tuple(f.get("contributes_to") or []),
            notes=f.get("notes", ""),
        )

    contexts: dict[str, ContextEntry] = {}
    for c in raw.get("contexts", []):
        status = c["status"]
        if status not in _VALID_STATUSES:
            raise ValueError(f"invalid status '{status}' for context {c['name']}")
        contexts[c["name"]] = ContextEntry(
            name=c["name"],
            logic_version=c["logic_version"],
            status=status,
            source_features=tuple(c.get("source_features") or []),
            logic_description=c.get("logic_description", ""),
            logic_fingerprint=c["logic_fingerprint"],
        )

    return FeatureRegistry(
        version=raw["version"],
        last_updated=raw["last_updated"],
        features=features,
        contexts=contexts,
        decision_versions=raw.get("decision_versions", {}),
    )


# Lazy-loaded singleton
_registry: FeatureRegistry | None = None


def get_registry() -> FeatureRegistry:
    global _registry
    if _registry is None:
        _registry = load_registry()
    return _registry
