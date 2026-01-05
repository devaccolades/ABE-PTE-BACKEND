import json
import re
from django.conf import settings
from openai import OpenAI

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

# -------------------------------------------------
# RULE QUESTION CONFIG (SOURCE OF TRUTH)
# -------------------------------------------------

RULE_QUESTION_CONFIG = {
    "fib_dropdown": {
        "answer_format": "mapping",
        "options_location": "subquestion",
        "correctness_type": "is_correct_flag",
    },
    "fib_drag_drop": {
        "answer_format": "mapping",
        "options_location": "question",
        "correctness_type": "order_position",
    },
    "mc_single": {
        "answer_format": "single_id",
        "options_location": "question",
        "correctness_type": "is_correct_flag",
    },
    "mc_multiple": {
        "answer_format": "list_of_ids",
        "options_location": "question",
        "correctness_type": "is_correct_flag",
    },
    "reorder_paragraphs": {
        "answer_format": "mapping",
        "options_location": "question",
        "correctness_type": "order_position",
    },
    "l_mc_single": {
        "answer_format": "single_id",
        "options_location": "question",
        "correctness_type": "is_correct_flag",
    },
    "l_mc_multiple": {
        "answer_format": "list_of_ids",
        "options_location": "question",
        "correctness_type": "is_correct_flag",
    },
    "l_fill_in_blanks": {
        "answer_format": "delimited_text",
        "options_location": "none",
        "correctness_type": "text_match",
    },
    "highlight_correct_summary": {
        "answer_format": "single_id",
        "options_location": "question",
        "correctness_type": "is_correct_flag",
    },
    "select_missing_word": {
        "answer_format": "single_id",
        "options_location": "question",
        "correctness_type": "is_correct_flag",
    },
    "highlight_incorrect_words": {
        "answer_format": "delimited_text",
        "options_location": "none",
        "correctness_type": "text_match",
    },
}


# -------------------------------------------------
# CORRECT DATA SERIALIZER (ORM → JSON)
# -------------------------------------------------

def extract_correct_data(*, question, subsection_name):
    cfg = RULE_QUESTION_CONFIG[subsection_name]

    if cfg["options_location"] == "question":
        return {
            "options": list(
                question.options.values(
                    "id",
                    "is_correct",
                    "order_position",
                    "option_text",
                )
            )
        }

    if cfg["options_location"] == "subquestion":
        return {
            "subquestions": [
                {
                    "blank_number": sq.blank_number,
                    "options": list(
                        sq.options.values(
                            "id",
                            "is_correct",
                            "option_text",
                        )
                    ),
                }
                for sq in question.sub_questions.all()
            ]
        }

    if cfg["options_location"] == "none":
        return {
            "text": question.text
        }

    return {}


# -------------------------------------------------
# PROMPT BUILDER (RULE-BASED, AI-EXECUTED)
# -------------------------------------------------

def build_rule_ai_prompt(*, user_answer, question, subsection):
    cfg = RULE_QUESTION_CONFIG.get(subsection.name)

    if not cfg:
        raise ValueError(
            f"No RULE_QUESTION_CONFIG defined for {subsection.name}"
        )

    payload = {
        "task_type": "rule_based",
        "question_type": subsection.name,
        "question_text": question.text,

        "answer_schema": cfg,

        # IMPORTANT: pass answer EXACTLY as stored
        "user_answer": user_answer.answer_data,

        # Explicit correctness data (no ORM concepts)
        "correct_data": extract_correct_data(
            question=question,
            subsection_name=subsection.name,
        ),

        # Rubric is the sole authority
        "rubric": subsection.rubric,

        # 🔒 NEW STRICT OUTPUT FORMAT
        "output_format": {
            "scores": {
                "<criterion_id>": {
                    "score": "number",
                    "max": "number"
                }
            },
            "feedback": "short 1 sentence"
        }
    }

    return json.dumps(payload, separators=(",", ":"))


def evaluate_with_ai(prompt: str):
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

        try:
            parsed = json.loads(raw_output)
        except:
            parsed = extract_json(raw_output)

        if not isinstance(parsed, dict):
            return {
                "success": False,
                "error": "Invalid JSON structure",
                "raw": raw_output,
            }

        # 🔒 CANONICAL NORMALIZATION (THIS IS THE FIX)
        normalized = {
            "evaluation": {
                "scores": parsed.get("scores", {}),
                "feedback": parsed.get("feedback", "")
            }
        }

        return {
            "success": True,
            "data": normalized,
            "raw": raw_output,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "raw": None,
        }

# -------------------------------------------------
# MAIN ENTRY POINT
# -------------------------------------------------



def run_rule_evaluation(*, user_answer, question, subsection):
    """
    Entry point for ALL rule-based evaluation.

    - Builds deterministic prompt
    - Calls AI evaluator
    - Returns AI output AS-IS
    """

    prompt = build_rule_ai_prompt(
        user_answer=user_answer,
        question=question,
        subsection=subsection,
    )

    # Imported AI evaluator
    evaluation_result = evaluate_with_ai(prompt)

    return {
        "ok": True,
        "evaluation": evaluation_result["data"],
    }
