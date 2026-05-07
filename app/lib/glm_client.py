"""GLM cloud client helpers for AI training plan generation."""

import json
import logging
import os
import time
from typing import Any
from urllib import request, error

# Import mock client for fallback
try:
    from .glm_mock import generate_plan_json_mock
except ImportError:
    generate_plan_json_mock = None

logger = logging.getLogger(__name__)

GLM_API_URL = os.getenv("GLM_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-5")
GLM_REQUEST_TIMEOUT = int(os.getenv("GLM_REQUEST_TIMEOUT", "60"))


class GlmClientError(RuntimeError):
    """Raised when GLM request fails or returns invalid payload."""


def _post_glm_payload(payload: dict[str, Any], max_retries: int = 2) -> dict[str, Any]:
    api_key = os.getenv("GLM_API_KEY")
    if not api_key:
        raise GlmClientError("GLM_API_KEY is not configured")

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            req = request.Request(
                GLM_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with request.urlopen(req, timeout=GLM_REQUEST_TIMEOUT) as res:
                raw = res.read().decode("utf-8")
            return json.loads(raw)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            last_error = GlmClientError(f"GLM HTTP {exc.code}: {body[:200]}")
            if exc.code >= 500 and attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise last_error from exc
        except (error.URLError, json.JSONDecodeError, Exception) as exc:
            last_error = GlmClientError(f"GLM request failed: {type(exc).__name__}: {str(exc)[:120]}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise last_error from exc
    raise last_error or GlmClientError("GLM request failed")


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract first JSON object from model output, tolerating fenced text around it."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise GlmClientError("Model did not return valid JSON.")

    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise GlmClientError("Model returned malformed JSON.") from exc


def generate_plan_json(prompt: str, max_retries: int = 2) -> dict[str, Any]:
    """Call GLM cloud model and return parsed JSON payload with retry logic."""
    api_key = os.getenv("GLM_API_KEY")
    
    # If no real API key, use mock client
    if not api_key:
        logger.warning("GLM_API_KEY not configured, using mock client")
        if generate_plan_json_mock:
            return generate_plan_json_mock(prompt)
        raise GlmClientError("GLM_API_KEY is not configured and mock client unavailable")

    payload = {
        "model": GLM_MODEL,
        "temperature": 0.3,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a running coach. Return only valid JSON with no markdown. "
                    "Follow requested schema exactly."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        logger.info("GLM plan request")
        obj = _post_glm_payload(payload, max_retries=max_retries)
        content = obj["choices"][0]["message"]["content"]
        return _extract_json_object(content)
    except GlmClientError:
        raise
    except Exception as exc:
        raise GlmClientError("Unexpected GLM response format.") from exc


def generate_short_suggestion(prompt: str, max_chars: int = 200, max_retries: int = 1) -> str:
    """
    Generate short plain-text suggestion using GLM and enforce character cap.
    """
    safe_max = max(80, min(max_chars, 200))
    api_key = os.getenv("GLM_API_KEY")
    if not api_key:
        # Deterministic fallback when GLM is unavailable.
        return "Keep an easy pace today, stay hydrated, and adjust effort if wind or heat increases."

    payload = {
        "model": GLM_MODEL,
        "temperature": 0.3,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a running coach. Return only one short plain text suggestion. "
                    f"Maximum {safe_max} characters. No markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    try:
        obj = _post_glm_payload(payload, max_retries=max_retries)
        content = str(obj["choices"][0]["message"]["content"]).strip()
    except Exception:
        # Never block UI suggestion flow when external model fails.
        return "Run at a controlled effort, hydrate early, and adjust pace to the current weather and wind."

    if len(content) > safe_max:
        content = content[:safe_max].rstrip(" ,;:.") + "."
    return content
