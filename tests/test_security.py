"""Tests for the security module: signed session tokens and in-memory rate limiter."""

from __future__ import annotations

import time

import pytest

from backend.security import (
    RateLimiter,
    RateLimitExceeded,
    TokenInvalid,
    create_token,
    verify_token,
)


# --- Tokens --------------------------------------------------------------


def test_token_roundtrip():
    token = create_token()
    # verify_token should not raise on a fresh token
    verify_token(token)


def test_token_has_two_parts():
    token = create_token()
    assert token.count(".") == 1
    payload_b64, sig_b64 = token.split(".")
    assert payload_b64 and sig_b64


def test_token_rejects_tampered_payload():
    token = create_token()
    payload_b64, sig_b64 = token.split(".")
    # Flip a character in the payload
    bad_payload = ("a" if payload_b64[0] != "a" else "b") + payload_b64[1:]
    tampered = f"{bad_payload}.{sig_b64}"
    with pytest.raises(TokenInvalid):
        verify_token(tampered)


def test_token_rejects_tampered_signature():
    token = create_token()
    payload_b64, sig_b64 = token.split(".")
    bad_sig = ("a" if sig_b64[0] != "a" else "b") + sig_b64[1:]
    tampered = f"{payload_b64}.{bad_sig}"
    with pytest.raises(TokenInvalid):
        verify_token(tampered)


def test_token_rejects_malformed():
    with pytest.raises(TokenInvalid):
        verify_token("not-a-real-token")
    with pytest.raises(TokenInvalid):
        verify_token("")
    with pytest.raises(TokenInvalid):
        verify_token("too.many.parts.here")


def test_token_rejects_expired():
    # ttl=0 means the token expires instantly
    token = create_token(ttl_seconds=0)
    time.sleep(0.01)
    with pytest.raises(TokenInvalid):
        verify_token(token)


def test_token_respects_ttl():
    token = create_token(ttl_seconds=60)
    # Should be valid now
    verify_token(token)


# --- Rate limiter --------------------------------------------------------


def test_rate_limiter_allows_within_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")  # third allowed


def test_rate_limiter_blocks_over_limit():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")
    with pytest.raises(RateLimitExceeded):
        limiter.check("1.2.3.4")


def test_rate_limiter_is_per_key():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.check("1.2.3.4")
    limiter.check("5.6.7.8")  # different key, should be allowed
    with pytest.raises(RateLimitExceeded):
        limiter.check("1.2.3.4")


def test_rate_limiter_recovers_after_window():
    limiter = RateLimiter(max_requests=1, window_seconds=0.05)
    limiter.check("1.2.3.4")
    with pytest.raises(RateLimitExceeded):
        limiter.check("1.2.3.4")
    time.sleep(0.1)
    # After window, should be allowed again
    limiter.check("1.2.3.4")
