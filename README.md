# VisionBoard

A single-page demo app where a student uploads images to a vision board, and
Claude (via LiteLLM) examines the images and returns 5–10 personalized
statements about aligned colleges and career paths. The student can agree,
disagree, or edit each statement to curate their final list.

Built for a CollegeBoard-style guidance-counselor demo.

## Stack

- **Backend:** FastAPI + LiteLLM + Claude (Anthropic)
- **Frontend:** Vanilla HTML / CSS / JS, no build step
- **Python:** 3.12+, managed with `uv`

## Setup

### Option 1: Run locally

```bash
# Install dependencies
uv sync

# Copy .env.example and set your Anthropic API key
cp .env.example .env
# then edit .env

# Run the dev server
uv run uvicorn backend.app:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

### Option 2: Run in GitHub Codespaces (public link)

1. Open this repo in a Codespace: **Code → Codespaces → Create codespace on main**
2. In Codespaces Settings, set the **`ANTHROPIC_API_KEY`** secret for this repository
   (Settings → Codespaces → Repository secrets → New secret)
3. The devcontainer auto-starts the server on port 8000 with `postAttachCommand`
4. Open the **Ports** panel, right-click port 8000, **Port Visibility → Public**
5. Click the globe icon next to port 8000 to open the public URL

## Usage

1. Drag images into the left panel (or click "Add Image")
2. Click "Analyze My Vision"
3. Review the reflections on the right — agree, disagree, or edit each one

## Tests

```bash
uv run pytest
```
