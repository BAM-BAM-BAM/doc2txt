"""Regression tests for the HMAC-wrapped classifier blob in doc2txt_learning.

These tests guarantee that:
- A classifier blob signed with `_sign_pickle` roundtrips through
  `_verify_and_strip` intact.
- Tampering with the blob, the signature, or the prefix marker is detected
  (returns None — caller retrains from raw samples).
- The HMAC key file is created with mode 0600 (or tightened on existing
  files) under the user's home directory.
- Missing signature prefix (legacy un-signed blobs) is rejected cleanly.

Covers CP-021 / SEC-A08-002. Without these tests, a future refactor
that removes `_verify_and_strip` would ship silently and re-expose the
pickle.loads RCE surface that existed pre-2026-04-24.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest import mock

import pytest

import doc2txt_learning as dl


def _isolated_key_path(tmp_path: Path) -> Path:
    """Point _HMAC_KEY_PATH at a tmpdir so tests don't mutate the real key."""
    return tmp_path / "classifier_hmac.key"


@pytest.fixture(autouse=True)
def isolated_key(tmp_path: Path, monkeypatch):
    """Each test gets a fresh HMAC key under tmp_path."""
    key_path = _isolated_key_path(tmp_path)
    monkeypatch.setattr(dl, "_HMAC_KEY_PATH", key_path)
    yield key_path


def test_sign_verify_roundtrip():
    """A blob signed and then verified returns the original bytes."""
    blob = b"arbitrary pickle bytes " * 50
    wrapped = dl._sign_pickle(blob)
    assert dl._verify_and_strip(wrapped) == blob


def test_tampered_blob_rejected():
    """Flipping a bit in the payload invalidates the signature."""
    blob = b"classifier serialized state"
    wrapped = dl._sign_pickle(blob)
    tampered = bytearray(wrapped)
    tampered[-1] ^= 1  # flip last bit of payload
    assert dl._verify_and_strip(bytes(tampered)) is None


def test_tampered_signature_rejected():
    """Flipping a bit inside the signature invalidates verification."""
    blob = b"any data"
    wrapped = dl._sign_pickle(blob)
    prefix_len = len(dl._HMAC_PREFIX)
    # Flip first signature byte
    tampered = bytearray(wrapped)
    tampered[prefix_len] ^= 1
    assert dl._verify_and_strip(bytes(tampered)) is None


def test_missing_prefix_rejected():
    """A raw pickle without the HMAC prefix is rejected — defends
    legacy unsigned blobs from being blindly trusted."""
    raw_unsigned = b"pickle-shaped bytes, no prefix"
    assert dl._verify_and_strip(raw_unsigned) is None


def test_truncated_blob_rejected():
    """A blob shorter than prefix+signature is rejected without crash."""
    # Just the prefix, no sig, no payload
    assert dl._verify_and_strip(dl._HMAC_PREFIX) is None
    # Prefix + partial sig
    assert dl._verify_and_strip(dl._HMAC_PREFIX + b"\x00" * 10) is None


def test_wrong_prefix_rejected():
    """A blob with a different format prefix is rejected — protects
    against format-version confusion attacks."""
    blob = b"data"
    # Craft a blob with a wrong 6-byte prefix but otherwise well-formed
    wrapped = dl._sign_pickle(blob)
    wrong = b"EVIL1\x00" + wrapped[len(dl._HMAC_PREFIX):]
    assert dl._verify_and_strip(wrong) is None


def test_hmac_key_file_is_0600(isolated_key: Path):
    """First call to _load_hmac_key creates the key file with mode 0600."""
    assert not isolated_key.exists()
    dl._load_hmac_key()  # trigger creation
    assert isolated_key.exists()
    mode = stat.S_IMODE(os.stat(isolated_key).st_mode)
    assert mode == 0o600, f"expected 0600, got 0o{mode:o}"


def test_hmac_key_persisted_across_calls(isolated_key: Path):
    """Two calls return the same key (persisted, not regenerated)."""
    key_a = dl._load_hmac_key()
    key_b = dl._load_hmac_key()
    assert key_a == key_b
    assert len(key_a) == 32  # 256-bit key


def test_sign_then_verify_with_wrong_key_fails(tmp_path: Path, monkeypatch):
    """A blob signed under one key cannot be verified under a different
    key — defends backup/restore scenarios where attacker gets the DB
    but not the user's HMAC key."""
    blob = b"payload"
    # Sign under the default tmp_path key
    wrapped = dl._sign_pickle(blob)

    # Move the key path to a new location (simulating the real key being
    # unavailable on a different machine/backup)
    new_key = tmp_path / "different.key"
    monkeypatch.setattr(dl, "_HMAC_KEY_PATH", new_key)

    # A fresh call will create a new random key at the new path
    assert dl._verify_and_strip(wrapped) is None
