"""Tests for the analyzer module.

We mock litellm.acompletion so the test runs without hitting the network,
but we verify that:
- The returned statements list matches the mocked LLM output
- The call was made with the expected model
- The user message contains both the text prompt and a base64 image part
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.analyzer import analyze_images


def _make_fake_response(statements: list[str]):
    """Build an object that mimics LiteLLM's response shape."""
    raw_content = json.dumps({"statements": statements})

    class _Msg:
        content = raw_content

    class _Choice:
        message = _Msg()

    class _Response:
        choices = [_Choice()]

    return _Response()


@pytest.mark.asyncio
async def test_analyze_images_returns_statements():
    fake_statements = [
        "You seem drawn to architecture and urban design — look at Cornell or Rice.",
        "Your creative spark suggests UX design or digital media programs.",
        "Consider liberal arts schools with strong design minors.",
        "Global issues matter to you — Georgetown or Tufts could fit.",
        "A hands-on maker ethos suggests engineering + art combined programs.",
        "You might thrive in small, collaborative studio environments.",
    ]
    fake_response = _make_fake_response(fake_statements)

    fake_image_bytes = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    with patch(
        "backend.analyzer.acompletion",
        new=AsyncMock(return_value=fake_response),
    ) as mock_acompletion:
        result = await analyze_images([(fake_image_bytes, "image/jpeg")])

    assert result == fake_statements
    assert len(result) == 6

    mock_acompletion.assert_called_once()
    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-4-5"
    assert call_kwargs["response_format"] == {"type": "json_object"}

    messages = call_kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "guidance counselor" in messages[0]["content"].lower()

    user_content = messages[1]["content"]
    assert isinstance(user_content, list)
    text_parts = [p for p in user_content if p["type"] == "text"]
    image_parts = [p for p in user_content if p["type"] == "image_url"]
    assert len(text_parts) == 1
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_analyze_images_handles_multiple_images():
    fake_statements = ["a", "b", "c", "d", "e"]
    fake_response = _make_fake_response(fake_statements)

    images = [
        (b"img1", "image/jpeg"),
        (b"img2", "image/png"),
        (b"img3", "image/webp"),
    ]

    with patch(
        "backend.analyzer.acompletion",
        new=AsyncMock(return_value=fake_response),
    ) as mock_acompletion:
        result = await analyze_images(images)

    assert result == fake_statements

    user_content = mock_acompletion.call_args.kwargs["messages"][1]["content"]
    image_parts = [p for p in user_content if p["type"] == "image_url"]
    assert len(image_parts) == 3
    assert image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert image_parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert image_parts[2]["image_url"]["url"].startswith("data:image/webp;base64,")
