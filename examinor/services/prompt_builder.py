# examinor/services/prompt_builder.py
import json
import hashlib
from django.utils.text import Truncator


def build_prompt(task_type: str, question_text: str, evaluation_payload: dict, rubric: dict):
    """
    Clean, deterministic, nano-friendly PTE evaluation prompt.
    """
    
    # -----------------------------
    # ANSWER + OPTIONAL METADATA
    # -----------------------------
    answer_text = evaluation_payload.get("answer_data") or ""
    analytics_block = ""

    if evaluation_payload.get("transcribed_audio_data"):
        ta = evaluation_payload["transcribed_audio_data"] or {}

        # transcript is the actual answer
        answer_text = (
            ta.get("transcription", {})
            .get("text", "")
        )

        # pass audio analytics AS-IS (may be empty / partial)
        analytics_block = json.dumps(
            ta,
            separators=(",", ":"),
        )

    answer_excerpt = Truncator(answer_text).chars(1500)

    # -----------------------------
    # COMPACT RUBRIC
    # -----------------------------
    compact_rubric = {}

    for key, value in rubric.items():
        max_score = 1

        if isinstance(value, dict):
            max_score = value.get("max") or value.get("max_score")
            if max_score is None:
                numeric_keys = [int(k) for k in value.keys() if str(k).isdigit()]
                max_score = max(numeric_keys) if numeric_keys else 1

        elif isinstance(value, list):
            max_score = len(value)

        compact_rubric[key] = {"max": max_score}

    rubric_json = json.dumps(compact_rubric, separators=(",", ":"))

    # -----------------------------
    # PROMPT
    # -----------------------------
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

ANALYTICS_METADATA (FOR ANALYSIS ONLY — NOT THE ANSWER):
{analytics_block}

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
