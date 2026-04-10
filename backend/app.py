"""FastAPI app for VisionBoard: serves the single-page frontend and the /api/analyze endpoint."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Load .env before we import anything that reads env vars
load_dotenv()

from .analyzer import analyze_images  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="VisionBoard")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.post("/api/analyze")
async def analyze(images: list[UploadFile] = File(...)):
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")

    try:
        image_data: list[tuple[bytes, str]] = []
        for img in images:
            data = await img.read()
            if not data:
                continue
            mime = img.content_type or "image/jpeg"
            image_data.append((data, mime))

        if not image_data:
            raise HTTPException(status_code=400, detail="Uploaded files were empty")

        logger.info("Received %d image(s) for analysis", len(image_data))
        statements = await analyze_images(image_data)
        return {"statements": statements}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Analyze failed")
        raise HTTPException(status_code=500, detail=str(e))
