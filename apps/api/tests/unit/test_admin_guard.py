"""Admin-1 — owner allowlist guard unit tests.

Covers is_owner: exact owner, case-insensitivity, empty allowlist denies,
non-owner/None/'' deny, multi-entry + whitespace trimming. (The require_owner
HTTP behavior — 404 for anon/non-owner — is verified live in the browser/API
tests; here we lock the pure allowlist logic.)
"""

import apps.api.src.api.admin_guard as g

OWNER = "kunalkhurana1@gmail.com"


def test_is_owner_true_for_owner(monkeypatch):
    monkeypatch.setattr(g.settings, "ARTHOS_OWNER_EMAILS", OWNER)
    assert g.is_owner(OWNER) is True


def test_is_owner_case_insensitive(monkeypatch):
    monkeypatch.setattr(g.settings, "ARTHOS_OWNER_EMAILS", "Kunalkhurana1@Gmail.COM")
    assert g.is_owner("KUNALKHURANA1@GMAIL.COM") is True
    assert g.is_owner(OWNER) is True


def test_empty_allowlist_denies_everyone(monkeypatch):
    monkeypatch.setattr(g.settings, "ARTHOS_OWNER_EMAILS", "")
    assert g.is_owner(OWNER) is False
    assert g.owner_emails() == set()


def test_non_owner_and_blank_denied(monkeypatch):
    monkeypatch.setattr(g.settings, "ARTHOS_OWNER_EMAILS", OWNER)
    assert g.is_owner("someone@else.com") is False
    assert g.is_owner(None) is False
    assert g.is_owner("") is False


def test_multi_entry_and_whitespace(monkeypatch):
    monkeypatch.setattr(g.settings, "ARTHOS_OWNER_EMAILS", f"  a@b.com , {OWNER} ")
    assert g.is_owner(OWNER) is True
    assert g.is_owner("a@b.com") is True
    assert g.is_owner("c@d.com") is False
