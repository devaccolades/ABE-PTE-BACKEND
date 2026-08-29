# examinor/services/prompt_builder.py
import json
import hashlib
from django.utils.text import Truncator


TEXT_ANSWER_KEYS = (
    "text",
    "answer_text",
    "response_text",
    "answer",
    "response",
    "value",
)


def normalize_answer_text(answer_data):
    if answer_data is None:
        return ""

    if isinstance(answer_data, str):
        return answer_data

    if isinstance(answer_data, (int, float, bool)):
        return str(answer_data)

    if isinstance(answer_data, list):
        return "\n".join(normalize_answer_text(item) for item in answer_data)

    if isinstance(answer_data, dict):
        for key in TEXT_ANSWER_KEYS:
            value = answer_data.get(key)
            if value not in (None, ""):
                return normalize_answer_text(value)

        return json.dumps(answer_data, ensure_ascii=False, sort_keys=True)

    return str(answer_data)


def build_prompt(task_type: str, question_text: str, evaluation_payload: dict, rubric: dict):
    """
    Clean, deterministic, nano-friendly PTE evaluation prompt.
    """
    
    # -----------------------------
    # ANSWER + OPTIONAL METADATA
    # -----------------------------
    answer_text = normalize_answer_text(evaluation_payload.get("answer_data"))
    reference_text = normalize_answer_text(
        evaluation_payload.get("reference_answer")
    )
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
    reference_excerpt = Truncator(reference_text).chars(3000)

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
    feedback_shape = '"<short, specific feedback in 1 sentence>"'
    feedback_rules = ""
    if task_type in {
        "summarize_written_text",
        "write_essay",
        "summarize_spoken_text",
    }:
        improvement = (
            "<one actionable improvement naming missing or inaccurate content>"
            if task_type == "summarize_spoken_text"
            else "<one actionable next step>"
        )
        feedback_shape = (
            '{"summary":"<specific overall assessment>",'
            '"strengths":"<specific strength grounded in the response>",'
            f'"improvements":"{improvement}",'
            '"errors":[{'
            '"type":"<spelling or grammar>",'
            '"text":"<exact verbatim error from the candidate response>",'
            '"suggestion":"<corrected text>",'
            '"explanation":"<brief reason>"}]}'
        )
        feedback_rules = """
- Return every clear spelling and grammar error in feedback.errors.
- error.type must be exactly "spelling" or "grammar".
- error.text must be an exact, case-preserving substring copied from CANDIDATE_RESPONSE.
- Keep error.text to the shortest useful word or phrase; do not paraphrase it.
- Do not include style preferences as grammar errors.
- Return an empty errors array when no clear spelling or grammar error exists.
"""
        if task_type == "summarize_spoken_text":
            feedback_rules += """
- Judge content only against REFERENCE_MATERIAL.
- Mention a concrete included, missing, or inaccurate idea in feedback.
- Do not give generic advice without an example from the response.
"""

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

REFERENCE_MATERIAL (source transcript, model answer, or key points):
\"\"\"{reference_excerpt}\"\"\"

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
{feedback_rules}

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
  "feedback": {feedback_shape}
}}

RULE:
Return ONLY valid JSON. No extra text.
"""

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    return prompt, prompt_hash
