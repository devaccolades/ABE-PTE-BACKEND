# examinor/services/prompt_builder.py
import json
import hashlib
from django.utils.text import Truncator


def build_prompt(task_type: str, question_text: str, answer_text: str, rubric: dict):
    """
    Clean, deterministic, nano-friendly PTE evaluation prompt.
    - Uses ONLY rubric keys + max values.
    - Forces model to NOT interpret or expand rubric.
    - Dynamic schema based on rubric dict.
    """

    # Keep model load small
    answer_excerpt = Truncator(answer_text or "").chars(1500)

    # Compact rubric: {criterion_id: {"max": X}}
    compact_rubric = {}
    for key, value in rubric.items():
        max_score = 1  # default

        if isinstance(value, dict):
            # 1. Check for explicit max / max_score
            max_score = value.get("max") or value.get("max_score")
            if max_score is None:
                # 2. Derive max from numeric keys
                numeric_keys = [int(k) for k in value.keys() if k.isdigit()]
                if numeric_keys:
                    max_score = max(numeric_keys)
                else:
                    max_score = 1  # fallback if keys are not numeric
        elif isinstance(value, list):
            # Optional: treat number of items as max, or default 1
            max_score = len(value)  # or set to 1 if each list is a single level
        else:
            # string → default 1
            max_score = 1

        compact_rubric[key] = {"max": max_score}

    rubric_json = json.dumps(compact_rubric, separators=(",", ":"))

    prompt = f"""
You are a strict, deterministic PTE examiner.
You MUST follow rubric keys EXACTLY as given.
Do NOT add new criteria.
Do NOT rename criteria.
Do NOT explain the rubric.
Do NOT infer missing rules.
Do NOT use holistic judgement.
Evaluate each criterion INDEPENDENTLY.

TASK_TYPE: {task_type}

QUESTION_TEXT:
{question_text}

CANDIDATE_RESPONSE:
\"\"\"{answer_excerpt}\"\"\"

RUBRIC_JSON (keys = criteria to score, each has a max):
{rubric_json}

SCORING INSTRUCTIONS:
- For EACH key in RUBRIC_JSON, assign:
    score = integer from 0 to max.
- Do NOT use decimals unless max > 1 and scaling requires it.
- Do NOT create weights unless explicitly given in rubric.
- weighted_score = sum(score values)
- max_score = sum(max values)

OUTPUT STRICTLY AS:
{{
  "scores": {{
      "<criterion_id>": {{
          "score": <number>,
          "max": <number>
      }}
  }},
  "weighted_score": <number>,
  "max_score": <number>,
  "feedback": "<short feedback in 1 sentence>"
}}

RULE:
Return ONLY valid JSON. No extra text.
"""

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    return prompt, prompt_hash
