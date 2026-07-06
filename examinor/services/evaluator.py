# examinor/services/evaluator.py

import json
import re
from django.conf import settings
from openai import OpenAI
from .openai_errors import format_openai_error


def get_openai_client():
    if not settings.OPENAI_API_KEY:
        return None

    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )


def extract_json(text: str):
    """
    Extract FIRST JSON object from the model output.
    Usually not needed because gpt-5-nano outputs clean JSON,
    but kept for safety.
    """
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except:
        pass
    return None


def evaluate_with_openai(prompt, phash):
    """
    Original working version, with safety upgrades.
    NO response_format, NO chat API.
    Uses Responses API exactly like before.
    """

    if not settings.OPENAI_API_KEY:
        return {
            "success": False,
            "error": "OPENAI_API_KEY is missing",
            "details": "Set OPENAI_API_KEY in the Django and Celery worker environment.",
            "raw": None,
            "prompt_hash": phash,
        }

    try:
        client = get_openai_client()

        # Minimal valid call – same as your old working version
        completion = client.responses.create(
            model=settings.OPENAI_EVALUATION_MODEL,
            input=prompt
        )

        # Same as old version: responses.create() → output_text
        raw_output = (completion.output_text or "").strip()

        # Try direct JSON parse (old behavior)
        try:
            parsed = json.loads(raw_output)
        except:
            # Fallback: regex extraction
            parsed = extract_json(raw_output)

        if parsed is None:
            return {
                "success": False,
                "error": "Failed to parse JSON.",
                "raw": raw_output,
                "prompt_hash": phash
            }

        return {
            "success": True,
            "data": parsed,
            "raw": raw_output,
            "prompt_hash": phash
        }

    except Exception as e:
        return {
            "success": False,
            "error": format_openai_error(e),
            "details": str(e),
            "raw": None,
            "prompt_hash": phash
        }
