# examinor/services/evaluator.py

import json
from django.conf import settings
from openai import OpenAI
from .prompt_builder import build_prompt

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def evaluate_with_openai(task_type, question_text, answer_text, rubric):
    prompt, phash = build_prompt(task_type, question_text, answer_text, rubric)

    try:
        # NO unsupported params. Minimal API.
        completion = client.responses.create(
            model="gpt-5-nano",
            input=prompt
        )

        # New OpenAI Response API format (2025):
        raw_output = completion.output_text

        parsed = json.loads(raw_output)

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
