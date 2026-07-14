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


class RuleConfigurationError(ValueError):
    pass


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
    correct_ids = set(
        question.options.filter(is_correct=True).values_list("id", flat=True)
    )
    if len(correct_ids) != 1:
        raise RuleConfigurationError(
            f"Question {question.pk} must have exactly one correct option."
        )
    if not selected_ids:
        return 0
    return 1 if selected_ids & correct_ids else 0


def _multiple_choice_ratio(question, answer_data):
    selected_ids = _as_id_set(answer_data)
    correct_ids = set(
        question.options.filter(is_correct=True).values_list("id", flat=True)
    )

    if not correct_ids:
        raise RuleConfigurationError(
            f"Question {question.pk} has no correct options."
        )

    correct_selected = len(selected_ids & correct_ids)
    incorrect_selected = len(selected_ids - correct_ids)
    awarded = max(correct_selected - incorrect_selected, 0)
    return awarded / len(correct_ids)


def _fib_dropdown_ratio(question, answer_data):
    answer = _as_mapping(answer_data)
    subquestions = list(question.sub_questions.prefetch_related("options"))

    if not subquestions:
        raise RuleConfigurationError(
            f"Question {question.pk} has no configured blanks."
        )

    awarded = 0
    for subquestion in subquestions:
        correct_count = subquestion.options.filter(is_correct=True).count()
        if correct_count != 1:
            raise RuleConfigurationError(
                f"Blank {subquestion.pk} must have exactly one correct option."
            )
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


def _submitted_position_mapping(answer_data, valid_option_ids):
    answer = _as_mapping(answer_data)
    submitted = {}

    for key, value in answer.items():
        key_as_int = _to_int(key)
        value_as_int = _to_int(value)

        # The exam frontend submits {blank_or_position: option_id}.
        if key_as_int is not None and value_as_int in valid_option_ids:
            submitted[key_as_int] = value_as_int
            continue

        # Keep compatibility with older {option_id: position} payloads.
        if key_as_int in valid_option_ids and value_as_int is not None:
            submitted[value_as_int] = key_as_int

    return submitted


def _fib_drag_drop_ratio(question, answer_data):
    correct_options = list(
        question.options.filter(
            is_correct=True,
            order_position__isnull=False,
        )
    )

    if not correct_options:
        raise RuleConfigurationError(
            f"Question {question.pk} has no correct drag-and-drop options."
        )

    valid_option_ids = set(
        question.options.values_list("id", flat=True)
    )
    submitted = _submitted_position_mapping(answer_data, valid_option_ids)
    correct_by_blank = {
        option.order_position: option.id
        for option in correct_options
    }
    if len(correct_by_blank) != len(correct_options):
        raise RuleConfigurationError(
            f"Question {question.pk} has duplicate correct blank positions."
        )

    awarded = sum(
        submitted.get(blank_position) == correct_option_id
        for blank_position, correct_option_id in correct_by_blank.items()
    )
    return awarded / len(correct_by_blank)


def _reorder_paragraphs_ratio(question, answer_data):
    ordered_options = list(
        question.options.exclude(order_position__isnull=True)
        .order_by("order_position", "id")
    )

    if len(ordered_options) < 2:
        raise RuleConfigurationError(
            f"Question {question.pk} needs at least two ordered paragraphs."
        )
    if len(ordered_options) != question.options.count():
        raise RuleConfigurationError(
            f"Every paragraph in question {question.pk} needs an order position."
        )
    positions = [option.order_position for option in ordered_options]
    if len(set(positions)) != len(positions):
        raise RuleConfigurationError(
            f"Question {question.pk} has duplicate paragraph positions."
        )

    valid_option_ids = {option.id for option in ordered_options}
    submitted = _submitted_position_mapping(answer_data, valid_option_ids)
    submitted_order = [
        option_id
        for _, option_id in sorted(submitted.items())
        if option_id in valid_option_ids
    ]
    expected_order = [option.id for option in ordered_options]

    expected_pairs = set(zip(expected_order, expected_order[1:]))
    submitted_pairs = set(zip(submitted_order, submitted_order[1:]))
    awarded = len(expected_pairs & submitted_pairs)

    return awarded / len(expected_pairs)


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
        raise RuleConfigurationError(
            f"Question {question.pk} has no configured correct text answers."
        )

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

    try:
        if subsection.name == "fib_dropdown":
            ratio = _fib_dropdown_ratio(question, user_answer.answer_data)
        elif subsection.name == "fib_drag_drop":
            ratio = _fib_drag_drop_ratio(question, user_answer.answer_data)
        elif subsection.name == "reorder_paragraphs":
            ratio = _reorder_paragraphs_ratio(question, user_answer.answer_data)
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
    except RuleConfigurationError as exc:
        return {
            "ok": False,
            "error": str(exc),
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
