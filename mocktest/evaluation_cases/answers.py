"""Build submissions in the exact payload shapes the exam frontend sends."""

import re

from examinor.scoring.task_contracts import AnswerKind, get_task_contract
from examinor.services.highlight_incorrect_words import (
    compare_displayed_text_to_source, tokenize_words,
)
from examinor.services.rule_evaluator import _configured_text_answers

from .schema import KeyAnswer


def build_submission(case, question):
    """Return (answer_data, transcribed_audio_data) for a case."""
    answer = case.answer
    if isinstance(answer, KeyAnswer):
        answer = build_key_answer(case.task, question, answer.variant)
    if get_task_contract(case.task).answer_kind == AnswerKind.AUDIO_UPLOAD:
        return None, {"transcription": {"text": answer}}
    return answer, None


def build_key_answer(task, question, variant):
    builder = BUILDERS.get(task)
    if builder is None:
        raise ValueError(f"No answer-key builder for {task}.")
    variants = builder(question)
    if variant not in variants:
        raise ValueError(f"{task} has no {variant!r} answer; choose from {sorted(variants)}.")
    return variants[variant]()


def _option_ids(question):
    options = list(question.options.order_by("id"))
    return (
        [option.id for option in options if option.is_correct],
        [option.id for option in options if not option.is_correct],
    )


def _single_choice(question):
    correct, wrong = _option_ids(question)
    # The frontend posts the bare option id.
    return {"correct": lambda: correct[0], "wrong": lambda: wrong[0]}


def _multiple_choice(question):
    correct, wrong = _option_ids(question)
    return {
        "correct": lambda: correct,
        "wrong": lambda: wrong,
        "one_correct": lambda: correct[:1],
        "correct_plus_wrong": lambda: correct + wrong[:1],
    }


def _fib_dropdown(question):
    blanks = list(question.sub_questions.order_by("blank_number").prefetch_related("options"))

    def pick(blank, correct):
        return next(option.id for option in blank.options.order_by("id") if option.is_correct == correct)

    # {blank_number: option_id}, keys stringified by JSON.
    return {
        "correct": lambda: {str(b.blank_number): pick(b, True) for b in blanks},
        "wrong": lambda: {str(b.blank_number): pick(b, False) for b in blanks},
        "first_correct": lambda: {
            str(b.blank_number): pick(b, index == 0) for index, b in enumerate(blanks)
        },
    }


def _fib_drag_drop(question):
    placed = list(
        question.options.filter(is_correct=True, order_position__isnull=False)
        .order_by("order_position")
    )
    ids = [option.id for option in placed]
    # {blank_position (1-based): option_id}; rotating the answers misplaces every one.
    return {
        "correct": lambda: {str(o.order_position): o.id for o in placed},
        "wrong": lambda: {
            str(o.order_position): ids[(index + 1) % len(ids)] for index, o in enumerate(placed)
        },
        "first_correct": lambda: {str(placed[0].order_position): placed[0].id},
    }


def _reorder(question):
    ordered = [o.id for o in question.options.order_by("order_position", "id")]

    def mapping(ids):
        return {str(position): option_id for position, option_id in enumerate(ids, start=1)}

    return {
        "correct": lambda: mapping(ordered),
        "reversed": lambda: mapping(ordered[::-1]),
        "swap_first_two": lambda: mapping([ordered[1], ordered[0], *ordered[2:]]),
    }


def _listening_blanks(question):
    answers = _configured_text_answers(question)
    # The frontend joins typed blanks with "|".
    return {
        "correct": lambda: "|".join(answers),
        "correct_uppercase": lambda: "|".join(answer.upper() for answer in answers),
        "wrong": lambda: "|".join("zzzz" for _ in answers),
        "first_correct": lambda: "|".join(
            [answers[0], *("zzzz" for _ in answers[1:])]
        ),
    }


def _highlight_incorrect(question):
    expected = compare_displayed_text_to_source(question.text, question.correct_answer).incorrect_words
    expected_indexes = {item.word_index for item in expected}
    extra = next(t for t in tokenize_words(question.text) if t.word_index not in expected_indexes)

    def selections(items):
        return {"selections": [{"word_index": i.word_index, "word": i.word} for i in items]}

    return {
        "correct": lambda: selections(expected),
        "correct_plus_extra": lambda: selections([*expected, extra]),
        "only_extra": lambda: selections([extra]),
    }


def _dictation(question):
    reference = question.correct_answer.strip()
    words = reference.split()
    longest = max(range(len(words)), key=lambda index: len(words[index]))

    def typo():
        changed = list(words)
        word = changed[longest]
        changed[longest] = word[0] + word[2] + word[1] + word[3:]
        return " ".join(changed)

    return {
        "exact": lambda: reference,
        "lowercase_no_punctuation": lambda: re.sub(r"[^\w\s']", "", reference).lower(),
        "missing_last_word": lambda: " ".join(words[:-1]),
        "one_typo": typo,
    }


BUILDERS = {
    "mc_single": _single_choice,
    "l_mc_single": _single_choice,
    "highlight_correct_summary": _single_choice,
    "select_missing_word": _single_choice,
    "mc_multiple": _multiple_choice,
    "l_mc_multiple": _multiple_choice,
    "fib_dropdown": _fib_dropdown,
    "fib_drag_drop": _fib_drag_drop,
    "reorder_paragraphs": _reorder,
    "l_fill_in_blanks": _listening_blanks,
    "highlight_incorrect_words": _highlight_incorrect,
    "write_from_dictation": _dictation,
}
