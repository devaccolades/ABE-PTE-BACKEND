# examinor/services/prompt_builder.py

import json
import hashlib
from django.utils.text import Truncator


def build_prompt(task_type: str, question_text: str, answer_text: str, rubric: dict):
    """
    Build a minimal PTE evaluation prompt.
    Uses ONLY task_type, question text, candidate answer, and rubric JSON.
    """

    answer_excerpt = Truncator(answer_text).chars(2000)
    rubric_json = json.dumps(rubric, separators=(",", ":"))

    prompt = f"""
You are a strict PTE examiner. Follow the rubric exactly.
Return ONLY valid JSON.

TASK TYPE:
{task_type}

QUESTION:
{question_text}

CANDIDATE RESPONSE:
\"\"\"{answer_excerpt}\"\"\"

RUBRIC_JSON:
{rubric_json}

REQUIRED OUTPUT FORMAT:
{{
  "scores": {{
      "<criterion_id>": {{
          "score": <number>,
          "max": <number>
      }}
  }},
  "weighted_score": <number>,
  "max_score": <number>,
  "feedback": "<short feedback>"
}}

Return ONLY the JSON.
"""

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    return prompt, prompt_hash
