"""Smoke tests – verify basic sanity and that the FastAPI app can be imported."""

from __future__ import annotations


def test_arithmetic() -> None:
    assert 1 + 1 == 2


def test_app_imports() -> None:
    """Ensure the FastAPI app object can be imported without raising."""
    from apps.api.src.main import app  # noqa: F401 – import as side-effect test
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
