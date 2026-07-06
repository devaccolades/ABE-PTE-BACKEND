import re
from examinor.scoring.validators import rubric_maxima

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


def _unwrap_answer(answer_data):
    if not isinstance(answer_data, dict):
        return answer_data

    for key in (
        "answer",
        "value",
        "selected",
        "selected_id",
        "selected_option",
        "selected_option_id",
        "selected_options",
        "selected_ids",
        "option_id",
        "option_ids",
        "choices",
        "text",
    ):
        if key in answer_data:
            return answer_data[key]

    return answer_data


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_id_set(answer_data):
    answer = _unwrap_answer(answer_data)

    if isinstance(answer, dict):
        answer = list(answer.values())

    if isinstance(answer, (list, tuple, set)):
        return {item for item in (_to_int(value) for value in answer) if item is not None}

    value = _to_int(answer)
    return {value} if value is not None else set()


def _as_mapping(answer_data):
    answer = _unwrap_answer(answer_data)

    if isinstance(answer, dict):
        return answer

    return {}


def _split_text_answer(answer_data):
    answer = _unwrap_answer(answer_data)

    if isinstance(answer, (list, tuple)):
        return [str(value).strip().lower() for value in answer if str(value).strip()]

    if answer is None:
        return []

    text = str(answer)
    parts = re.split(r"[,|\n;]+", text)
    return [part.strip().lower() for part in parts if part.strip()]


def _score_from_ratio(ratio, rubric):
    maxima = rubric_maxima(rubric)

    if not maxima:
        return {
            "score": {
                "score": round(ratio, 2),
                "max": 1.0,
            }
        }

    return {
        key: {
            "score": round(max_score * ratio, 2),
            "max": max_score,
        }
        for key, max_score in maxima.items()
    }


def _single_choice_ratio(question, answer_data):
    selected_ids = _as_id_set(answer_data)
    if not selected_ids:
        return 0

    correct_ids = set(
        question.options.filter(is_correct=True).values_list("id", flat=True)
    )
    return 1 if selected_ids & correct_ids else 0


def _multiple_choice_ratio(question, answer_data):
    selected_ids = _as_id_set(answer_data)
    correct_ids = set(
        question.options.filter(is_correct=True).values_list("id", flat=True)
    )

    if not correct_ids:
        return 0

    correct_selected = len(selected_ids & correct_ids)
    incorrect_selected = len(selected_ids - correct_ids)
    awarded = max(correct_selected - incorrect_selected, 0)
    return awarded / len(correct_ids)


def _fib_dropdown_ratio(question, answer_data):
    answer = _as_mapping(answer_data)
    subquestions = list(question.sub_questions.prefetch_related("options"))

    if not subquestions:
        return 0

    awarded = 0
    for subquestion in subquestions:
        selected = (
            answer.get(str(subquestion.blank_number))
            or answer.get(subquestion.blank_number)
            or answer.get(str(subquestion.id))
            or answer.get(subquestion.id)
        )
        selected_id = _to_int(selected)
        if selected_id is None:
            continue

        if subquestion.options.filter(id=selected_id, is_correct=True).exists():
            awarded += 1

    return awarded / len(subquestions)


def _order_ratio(question, answer_data):
    answer = _as_mapping(answer_data)
    ordered_options = list(
        question.options.exclude(order_position__isnull=True)
    )

    if not ordered_options:
        return 0

    awarded = 0
    for option in ordered_options:
        submitted_position = (
            answer.get(str(option.id))
            or answer.get(option.id)
        )

        if submitted_position is None:
            for key, value in answer.items():
                if _to_int(value) == option.id:
                    submitted_position = key
                    break

        if _to_int(submitted_position) == option.order_position:
            awarded += 1

    return awarded / len(ordered_options)


def _text_match_ratio(question, answer_data):
    answers = _split_text_answer(answer_data)
    correct_answers = [
        subquestion.correct_answer.strip().lower()
        for subquestion in question.sub_questions.all()
        if subquestion.correct_answer
    ]

    if not correct_answers and question.correct_answer:
        correct_answers = _split_text_answer(question.correct_answer)

    if not correct_answers:
        return 0

    awarded = 0
    for index, correct in enumerate(correct_answers):
        if index < len(answers) and answers[index] == correct:
            awarded += 1

    return awarded / len(correct_answers)


def evaluate_deterministically(*, user_answer, question, subsection):
    cfg = RULE_QUESTION_CONFIG.get(subsection.name)
    if not cfg:
        return {
            "ok": False,
            "error": f"No rule configuration defined for {subsection.name}",
        }

    if subsection.name == "fib_dropdown":
        ratio = _fib_dropdown_ratio(question, user_answer.answer_data)
    elif cfg["correctness_type"] == "order_position":
        ratio = _order_ratio(question, user_answer.answer_data)
    elif cfg["correctness_type"] == "text_match":
        ratio = _text_match_ratio(question, user_answer.answer_data)
    elif cfg["correctness_type"] == "is_correct_flag":
        if cfg["answer_format"] == "list_of_ids":
            ratio = _multiple_choice_ratio(question, user_answer.answer_data)
        else:
            ratio = _single_choice_ratio(question, user_answer.answer_data)
    else:
        return {
            "ok": False,
            "error": f"Unsupported rule correctness type {cfg['correctness_type']}",
        }

    ratio = max(min(ratio, 1), 0)
    scores = _score_from_ratio(ratio, subsection.rubric)

    return {
        "ok": True,
        "evaluation": {
            "scores": scores,
            "weighted_score": sum(item["score"] for item in scores.values()),
            "max_score": sum(item["max"] for item in scores.values()),
            "feedback": "Correct." if ratio == 1 else "Some answers were incorrect.",
        },
    }


def run_rule_evaluation(*, user_answer, question, subsection):
    """
    Entry point for ALL rule-based evaluation.

    Objective question types are evaluated locally to avoid OpenAI latency,
    timeout, and rate-limit risk.
    """
    return evaluate_deterministically(
        user_answer=user_answer,
        question=question,
        subsection=subsection,
    )
