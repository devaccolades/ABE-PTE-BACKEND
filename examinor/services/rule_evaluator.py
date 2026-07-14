from collections import Counter
from difflib import SequenceMatcher
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
        "correctness_type": "penalized_word_selection",
    },
    "write_from_dictation": {
        "answer_format": "free_text",
        "options_location": "none",
        "correctness_type": "word_sequence",
    },
}


class RuleConfigurationError(ValueError):
    pass


def uses_rule_evaluation(subsection):
    return (
        subsection.name in RULE_QUESTION_CONFIG
        or subsection.evaluation_type == "rule"
    )


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

    if isinstance(answer, dict):
        def sort_key(item):
            key = _to_int(item[0])
            return (key is None, key if key is not None else str(item[0]))

        answer = [value for _, value in sorted(answer.items(), key=sort_key)]

    if isinstance(answer, (list, tuple)):
        return [str(value).strip().lower() for value in answer if str(value).strip()]

    if answer is None:
        return []

    text = str(answer)
    parts = re.split(r"[,|\n;]+", text)
    return [part.strip().lower() for part in parts if part.strip()]


WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)


def _word_tokens(value):
    return [token.lower() for token in WORD_RE.findall(str(value or ""))]


def _normalized_text(value):
    return " ".join(_word_tokens(value))


def _configured_text_answers(question):
    answers = [
        subquestion.correct_answer
        for subquestion in question.sub_questions.order_by("blank_number", "id")
        if subquestion.correct_answer
    ]
    if not answers and question.correct_answer:
        answers = _split_text_answer(question.correct_answer)
    return [answer for answer in answers if _normalized_text(answer)]


def _dictation_reference(question):
    reference = question.correct_answer
    if not _word_tokens(reference):
        raise RuleConfigurationError(
            f"Question {question.pk} has no configured dictation transcript."
        )
    return reference


def _write_from_dictation_ratio(question, answer_data):
    expected = _word_tokens(_dictation_reference(question))
    submitted = _word_tokens(_unwrap_answer(answer_data))
    matcher = SequenceMatcher(None, expected, submitted, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(expected)


def _looks_like_word_list(value):
    text = str(value or "")
    if any(separator in text for separator in ("|", ";", "\n")):
        return True
    parts = [part.strip() for part in text.split(",") if part.strip()]
    return (
        len(parts) > 1
        and sum(len(_word_tokens(part)) for part in parts) <= 24
        and all(len(_word_tokens(part)) <= 4 for part in parts)
    )


def _highlight_incorrect_expected_words(question):
    configured = _configured_text_answers(question)
    if question.sub_questions.exists() or _looks_like_word_list(question.correct_answer):
        return [word for answer in configured for word in _word_tokens(answer)]

    reference = question.correct_answer
    displayed = question.text
    if not _word_tokens(reference) or not _word_tokens(displayed):
        raise RuleConfigurationError(
            f"Question {question.pk} needs incorrect words or a reference transcript."
        )

    displayed_words = WORD_RE.findall(displayed)
    displayed_normalized = [word.lower() for word in displayed_words]
    reference_normalized = _word_tokens(reference)
    matcher = SequenceMatcher(
        None,
        displayed_normalized,
        reference_normalized,
        autojunk=False,
    )
    incorrect = []
    for tag, start, end, _, _ in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            incorrect.extend(displayed_normalized[start:end])

    if not incorrect:
        raise RuleConfigurationError(
            f"Question {question.pk} has no detectable incorrect transcript words."
        )
    return incorrect


def _highlight_incorrect_ratio(question, answer_data):
    selected = Counter(
        word
        for answer in _split_text_answer(answer_data)
        for word in _word_tokens(answer)
    )
    expected = Counter(_highlight_incorrect_expected_words(question))
    correct_selected = sum((selected & expected).values())
    incorrect_selected = sum((selected - expected).values())
    awarded = max(correct_selected - incorrect_selected, 0)
    return awarded / sum(expected.values())


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
    correct_answers = _configured_text_answers(question)

    if not correct_answers:
        raise RuleConfigurationError(
            f"Question {question.pk} has no configured correct text answers."
        )

    awarded = 0
    for index, correct in enumerate(correct_answers):
        if (
            index < len(answers)
            and _normalized_text(answers[index]) == _normalized_text(correct)
        ):
            awarded += 1

    return awarded / len(correct_answers)


def _option_text(option):
    return str(option.option_text or f"Option {option.pk}").strip()


def _feedback_status(ratio):
    if ratio >= 1:
        return "correct"
    if ratio <= 0:
        return "incorrect"
    return "partial"


def _single_choice_feedback(question, answer_data, ratio):
    options = {option.id: option for option in question.options.all()}
    selected_ids = _as_id_set(answer_data)
    correct_ids = {option.id for option in options.values() if option.is_correct}
    return {
        "summary": "Correct answer selected." if ratio == 1 else "The selected answer was incorrect.",
        "details": [{
            "label": "Answer",
            "status": _feedback_status(ratio),
            "selected": ", ".join(
                _option_text(options[option_id])
                for option_id in selected_ids
                if option_id in options
            ) or "No answer",
            "correct": ", ".join(
                _option_text(options[option_id])
                for option_id in correct_ids
            ),
        }],
    }


def _multiple_choice_feedback(question, answer_data, ratio):
    options = {option.id: option for option in question.options.all()}
    selected_ids = _as_id_set(answer_data)
    correct_ids = {option.id for option in options.values() if option.is_correct}
    correct_selected = selected_ids & correct_ids
    incorrect_selected = selected_ids - correct_ids
    missed = correct_ids - selected_ids
    summary = (
        f"Selected {len(correct_selected)} correct option(s), "
        f"{len(incorrect_selected)} incorrect option(s), and missed {len(missed)} correct option(s)."
    )
    return {
        "summary": summary,
        "details": [{
            "label": "Selections",
            "status": _feedback_status(ratio),
            "selected": ", ".join(
                _option_text(options[option_id])
                for option_id in selected_ids
                if option_id in options
            ) or "No answer",
            "correct": ", ".join(
                _option_text(options[option_id])
                for option_id in correct_ids
            ),
        }],
    }


def _fib_dropdown_feedback(question, answer_data, ratio):
    answer = _as_mapping(answer_data)
    details = []
    correct_count = 0
    subquestions = list(question.sub_questions.prefetch_related("options"))
    for subquestion in subquestions:
        options = {option.id: option for option in subquestion.options.all()}
        correct = next(option for option in options.values() if option.is_correct)
        selected_id = _to_int(
            answer.get(str(subquestion.blank_number))
            or answer.get(subquestion.blank_number)
            or answer.get(str(subquestion.id))
            or answer.get(subquestion.id)
        )
        is_correct = selected_id == correct.id
        correct_count += int(is_correct)
        details.append({
            "label": f"Blank {subquestion.blank_number}",
            "status": "correct" if is_correct else "incorrect",
            "selected": _option_text(options[selected_id]) if selected_id in options else "No answer",
            "correct": _option_text(correct),
        })
    return {
        "summary": f"{correct_count} of {len(details)} blanks were correct.",
        "details": details,
    }


def _fib_drag_drop_feedback(question, answer_data, ratio):
    options = {option.id: option for option in question.options.all()}
    submitted = _submitted_position_mapping(answer_data, set(options))
    correct_by_blank = {
        option.order_position: option
        for option in options.values()
        if option.is_correct and option.order_position is not None
    }
    details = []
    correct_count = 0
    for blank_position, correct in sorted(correct_by_blank.items()):
        selected_id = submitted.get(blank_position)
        is_correct = selected_id == correct.id
        correct_count += int(is_correct)
        details.append({
            "label": f"Blank {blank_position}",
            "status": "correct" if is_correct else "incorrect",
            "selected": _option_text(options[selected_id]) if selected_id in options else "No answer",
            "correct": _option_text(correct),
        })
    return {
        "summary": f"{correct_count} of {len(details)} blanks were correct.",
        "details": details,
    }


def _reorder_feedback(question, answer_data, ratio):
    options = list(question.options.all())
    by_id = {option.id: option for option in options}
    valid_ids = set(by_id)
    submitted = _submitted_position_mapping(answer_data, valid_ids)
    submitted_order = [option_id for _, option_id in sorted(submitted.items())]
    expected_order = [
        option.id
        for option in sorted(options, key=lambda option: (option.order_position, option.id))
    ]
    expected_pairs = set(zip(expected_order, expected_order[1:]))
    submitted_pairs = set(zip(submitted_order, submitted_order[1:]))
    correct_pairs = len(expected_pairs & submitted_pairs)
    return {
        "summary": f"{correct_pairs} of {len(expected_pairs)} adjacent paragraph pair(s) were correct.",
        "details": [{
            "label": "Paragraph order",
            "status": _feedback_status(ratio),
            "selected": " -> ".join(_option_text(by_id[option_id]) for option_id in submitted_order) or "No answer",
            "correct": " -> ".join(_option_text(by_id[option_id]) for option_id in expected_order),
        }],
    }


def _text_match_feedback(question, answer_data, ratio):
    selected = _split_text_answer(answer_data)
    correct = _configured_text_answers(question)
    details = []
    for index, expected in enumerate(correct, start=1):
        actual = selected[index - 1] if index <= len(selected) else "No answer"
        details.append({
            "label": f"Answer {index}",
            "status": "correct" if _normalized_text(actual) == _normalized_text(expected) else "incorrect",
            "selected": actual,
            "correct": expected,
        })
    correct_count = sum(detail["status"] == "correct" for detail in details)
    return {
        "summary": f"{correct_count} of {len(details)} answer(s) were correct.",
        "details": details,
    }


def _write_from_dictation_feedback(question, answer_data, ratio):
    reference = _dictation_reference(question)
    selected = str(_unwrap_answer(answer_data) or "").strip()
    expected_words = _word_tokens(reference)
    selected_words = _word_tokens(selected)
    matcher = SequenceMatcher(None, expected_words, selected_words, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return {
        "summary": f"{matched} of {len(expected_words)} words were correct and in sequence.",
        "details": [{
            "label": "Dictation",
            "status": _feedback_status(ratio),
            "selected": selected or "No answer",
            "correct": reference,
        }],
    }


def _highlight_incorrect_feedback(question, answer_data, ratio):
    selected = [
        word
        for answer in _split_text_answer(answer_data)
        for word in _word_tokens(answer)
    ]
    expected = _highlight_incorrect_expected_words(question)
    selected_counter = Counter(selected)
    expected_counter = Counter(expected)
    correct_selected = sum((selected_counter & expected_counter).values())
    incorrect_selected = sum((selected_counter - expected_counter).values())
    missed = sum((expected_counter - selected_counter).values())
    return {
        "summary": (
            f"Selected {correct_selected} correct word(s), "
            f"{incorrect_selected} incorrect word(s), and missed {missed}."
        ),
        "details": [{
            "label": "Highlighted words",
            "status": _feedback_status(ratio),
            "selected": ", ".join(selected) or "No answer",
            "correct": ", ".join(expected),
        }],
    }


def build_rule_feedback(*, question, subsection, answer_data, ratio):
    if subsection.name == "fib_dropdown":
        feedback = _fib_dropdown_feedback(question, answer_data, ratio)
    elif subsection.name == "fib_drag_drop":
        feedback = _fib_drag_drop_feedback(question, answer_data, ratio)
    elif subsection.name == "reorder_paragraphs":
        feedback = _reorder_feedback(question, answer_data, ratio)
    elif subsection.name == "write_from_dictation":
        feedback = _write_from_dictation_feedback(question, answer_data, ratio)
    elif subsection.name == "highlight_incorrect_words":
        feedback = _highlight_incorrect_feedback(question, answer_data, ratio)
    elif subsection.name in {"mc_multiple", "l_mc_multiple"}:
        feedback = _multiple_choice_feedback(question, answer_data, ratio)
    elif subsection.name in {
        "mc_single",
        "l_mc_single",
        "highlight_correct_summary",
        "select_missing_word",
    }:
        feedback = _single_choice_feedback(question, answer_data, ratio)
    else:
        feedback = _text_match_feedback(question, answer_data, ratio)

    feedback["explanation"] = question.answer_explanation or ""
    return feedback


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
        elif subsection.name == "write_from_dictation":
            ratio = _write_from_dictation_ratio(question, user_answer.answer_data)
        elif subsection.name == "highlight_incorrect_words":
            ratio = _highlight_incorrect_ratio(question, user_answer.answer_data)
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
    feedback = build_rule_feedback(
        question=question,
        subsection=subsection,
        answer_data=user_answer.answer_data,
        ratio=ratio,
    )

    return {
        "ok": True,
        "evaluation": {
            "scores": scores,
            "weighted_score": sum(item["score"] for item in scores.values()),
            "max_score": sum(item["max"] for item in scores.values()),
            "feedback": feedback,
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
