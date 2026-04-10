"""Session tokens and rate limiting for VisionBoard.

- create_token() / verify_token() — HMAC-signed short-lived session tokens.
  Embedded in the HTML page on GET /, required as X-VB-Token on POST /api/analyze.
  This means a client must first load the page to get a token, making it
  harder for someone to hit the API cold with no browser interaction.

- RateLimiter — simple in-memory sliding-window limiter keyed by client IP
  (primary defense against runaway cost if someone does scrape the token).

Both are intentionally no-dependency, stdlib-only.
"""

from __future__ import annotations

import base64
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from hashlib import sha256
from threading import Lock

# One random secret per server process. Restarting the server invalidates
# all tokens, which is the desired behavior for a demo.
_SERVER_SECRET: bytes = secrets.token_bytes(32)

# Default token lifetime: 30 min
DEFAULT_TTL_SECONDS = 30 * 60


class TokenInvalid(Exception):
    """Raised when a token fails to verify (malformed, bad signature, expired)."""


class RateLimitExceeded(Exception):
    """Raised when a client exceeds the configured rate limit."""

    def __init__(self, retry_after_seconds: float):
        super().__init__(f"Rate limit exceeded. Retry after {retry_after_seconds:.0f}s.")
        self.retry_after_seconds = retry_after_seconds


# --- Tokens --------------------------------------------------------------


def create_token(ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Return a short-lived HMAC-signed token: `<payload_b64>.<sig_b64>`."""
    payload = {"exp": int(time.time()) + int(ttl_seconds)}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url(payload_bytes)
    sig = hmac.new(_SERVER_SECRET, payload_b64.encode("ascii"), sha256).digest()
    sig_b64 = _b64url(sig)
    return f"{payload_b64}.{sig_b64}"


def verify_token(token: str) -> None:
    """Raise TokenInvalid if the token is malformed, tampered with, or expired."""
    if not token or not isinstance(token, str):
        raise TokenInvalid("missing token")
    parts = token.split(".")
    if len(parts) != 2:
        raise TokenInvalid("malformed token")
    payload_b64, sig_b64 = parts

    expected_sig = hmac.new(_SERVER_SECRET, payload_b64.encode("ascii"), sha256).digest()
    try:
        provided_sig = _b64url_decode(sig_b64)
    except Exception as e:
        raise TokenInvalid("bad signature encoding") from e

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise TokenInvalid("bad signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as e:
        raise TokenInvalid("bad payload encoding") from e

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise TokenInvalid("missing exp claim")
    if time.time() > exp:
        raise TokenInvalid("token expired")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


# --- Rate limiter --------------------------------------------------------


class RateLimiter:
    """Simple in-memory sliding-window rate limiter keyed by an arbitrary string.

    Not thread-safe across multiple worker processes, but FastAPI/uvicorn with
    a single worker (which is what we run) is fine. A lock guards against
    concurrent coroutines in the same event loop.
    """

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        """Record a request from `key`. Raise RateLimitExceeded if the key is over limit."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry_after = max(0.0, self.window_seconds - (now - bucket[0]))
                raise RateLimitExceeded(retry_after_seconds=retry_after)
            bucket.append(now)
