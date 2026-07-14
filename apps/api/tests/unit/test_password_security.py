"""Auth hardening — password hashing bounds + algorithm (Phase 3).

Locks the safe scrypt config and the 8..256 length bounds so a future change
can't silently weaken hashing or reintroduce the long-input DoS path.
"""

import time

import pytest

from apps.api.src.auth import identity as ident


def test_hash_uses_scrypt_with_salt():
    enc = ident.hash_password("password123")
    assert enc.startswith("scrypt$")
    parts = enc.split("$")
    assert parts[0] == "scrypt" and int(parts[1]) >= 2 ** 14  # N cost
    # two different hashes for the same password => per-password random salt
    assert ident.hash_password("password123") != enc


def test_roundtrip_verify():
    enc = ident.hash_password("correct horse battery")
    assert ident.verify_password("correct horse battery", enc) is True
    assert ident.verify_password("wrong", enc) is False
    assert ident.verify_password("", enc) is False
    assert ident.verify_password("x", None) is False


def test_min_length_enforced():
    with pytest.raises(ValueError):
        ident.hash_password("short")          # < 8


def test_max_length_blocks_long_input_dos():
    # hashing a 1 MB password must be rejected, not fed to scrypt.
    with pytest.raises(ValueError):
        ident.hash_password("a" * 1_000_000)


def test_verify_rejects_overlong_without_hashing():
    enc = ident.hash_password("password123")
    t = time.time()
    assert ident.verify_password("a" * 1_000_000, enc) is False
    # rejected by the length guard => effectively instant (no scrypt run)
    assert time.time() - t < 0.5
