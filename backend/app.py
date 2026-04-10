"""FastAPI app for VisionBoard: serves the single-page frontend and the /api/analyze endpoint.

Security:
- GET / injects a short-lived HMAC-signed session token into a meta tag.
- POST /api/analyze requires that token in the X-VB-Token header.
- POST /api/analyze is rate-limited per client IP and globally.
"""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Load .env before we import anything that reads env vars
load_dotenv()

from .analyzer import analyze_images  # noqa: E402
from .security import (  # noqa: E402
    RateLimitExceeded,
    RateLimiter,
    TokenInvalid,
    create_token,
    verify_token,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="VisionBoard")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
INDEX_PATH = FRONTEND_DIR / "index.html"

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# --- Rate limits ---------------------------------------------------------
# Per-IP: 5 analyses per 10 minutes (~30/hour). Enough for a demo flow.
# Global:  40 analyses per hour. Insurance cap on Anthropic spend.
_per_ip_limiter = RateLimiter(max_requests=5, window_seconds=600)
_global_limiter = RateLimiter(max_requests=40, window_seconds=3600)


@app.get("/", response_class=HTMLResponse)
async def root():
    html = INDEX_PATH.read_text(encoding="utf-8")
    token = create_token()
    html = html.replace("__VB_TOKEN__", token)
    return HTMLResponse(content=html)


@app.get("/favicon.ico")
async def favicon():
    # No favicon shipped; return 204 so browsers stop hammering the route.
    return HTMLResponse(status_code=204)


@app.post("/api/analyze")
async def analyze(
    request: Request,
    images: list[UploadFile] = File(...),
    x_vb_token: str | None = Header(default=None, alias="X-VB-Token"),
):
    # 1. Token check (required)
    if not x_vb_token:
        raise HTTPException(status_code=401, detail="Missing session token")
    try:
        verify_token(x_vb_token)
    except TokenInvalid as e:
        raise HTTPException(status_code=401, detail=f"Invalid session token: {e}")

    # 2. Rate limit by client IP, then globally
    client_ip = _client_ip(request)
    try:
        _per_ip_limiter.check(client_ip)
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=429,
            detail="Too many requests from your IP. Please wait a bit and try again.",
            headers={"Retry-After": str(int(e.retry_after_seconds))},
        )
    try:
        _global_limiter.check("__global__")
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=429,
            detail="VisionBoard is at capacity right now. Please try again later.",
            headers={"Retry-After": str(int(e.retry_after_seconds))},
        )

    # 3. Image validation
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")

    image_data: list[tuple[bytes, str]] = []
    for img in images:
        data = await img.read()
        if not data:
            continue
        mime = img.content_type or "image/jpeg"
        image_data.append((data, mime))

    if not image_data:
        raise HTTPException(status_code=400, detail="Uploaded files were empty")

    logger.info(
        "Analyzing %d image(s) for client=%s (token ok)", len(image_data), client_ip
    )

    try:
        statements = await analyze_images(image_data)
    except Exception as e:
        logger.exception("Analyze failed")
        raise HTTPException(status_code=500, detail=str(e))

    return {"statements": statements}


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Prefers X-Forwarded-For because Codespaces
    and most reverse proxies set it; falls back to the socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
