# examinor/services/evaluator.py

import json
import re
from django.conf import settings
from openai import OpenAI
from .prompt_builder import build_prompt

client = OpenAI(api_key=settings.OPENAI_API_KEY)


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

    try:
        # Minimal valid call – same as your old working version
        completion = client.responses.create(
            model="gpt-5-nano",
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
            "error": str(e),
            "raw": None,
            "prompt_hash": phash
        }
