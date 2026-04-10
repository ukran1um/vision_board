"""Vision-board analyzer: base64-encode images, call Claude via LiteLLM, parse JSON."""

from __future__ import annotations

import base64
import json
import logging
import re

from litellm import acompletion

from .config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a thoughtful college and career guidance counselor at CollegeBoard.
A student has built a vision board from images that inspire them. Look at their board as a
whole — a collage representing who they are, what draws them, and where they want to go —
and produce between 5 and 10 concrete, personalized statements about what this vision
suggests for their college and career path.

Each statement should:
- Be warm, specific, and actionable (not generic platitudes)
- Reference concrete college types, majors, programs, or career paths where it fits
- Feel like insight from a trusted mentor, not a horoscope
- Be 1–3 sentences long

Look for patterns across the images: recurring colors, settings, objects, people, moods.
Name what you notice before drawing conclusions. If the student's vision is ambiguous or
contradictory, say so honestly rather than inventing a narrative.

Return your response as JSON with this exact shape:
{"statements": ["statement 1", "statement 2", ...]}
"""

USER_PROMPT = (
    "Here is my vision board. Look at these images as a whole and tell me what they "
    "suggest about who I am and what colleges or careers might align with me."
)


async def analyze_images(images: list[tuple[bytes, str]]) -> list[str]:
    """Analyze a list of (image_bytes, mime_type) tuples and return 5–10 guidance statements."""
    if not images:
        raise ValueError("analyze_images requires at least one image")

    settings = get_settings()

    content: list[dict] = [{"type": "text", "text": USER_PROMPT}]
    for img_bytes, mime in images:
        # Normalize mime type — LiteLLM/Anthropic wants image/jpeg, image/png, image/webp, image/gif
        if not mime or not mime.startswith("image/"):
            mime = "image/jpeg"
        b64 = base64.b64encode(img_bytes).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    logger.info("Analyzing %d image(s) with model %s", len(images), settings.MODEL)

    response = await acompletion(
        model=settings.MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = _parse_json(raw)

    statements = data.get("statements")
    if not isinstance(statements, list) or not statements:
        raise RuntimeError(f"LLM returned unexpected payload: {raw!r}")

    return [str(s).strip() for s in statements if str(s).strip()]


def _parse_json(text: str) -> dict:
    """Parse JSON from the LLM response, tolerating markdown fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from a markdown code fence
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Last resort: find the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise RuntimeError(f"Could not parse JSON from LLM response: {text!r}")
