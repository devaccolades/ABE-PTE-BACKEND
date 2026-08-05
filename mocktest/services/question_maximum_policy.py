import math
import re
from dataclasses import dataclass


VALID_SKILLS = ("speaking", "writing", "reading", "listening")
WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
BLANK_RE = re.compile(r"----|_{2,}")


@dataclass(frozen=True, slots=True)
class SkillMaximumExpectation:
    skill: str
    maximum: float
    basis: str


FIXED_TASK_MAXIMA = {
    "repeat_sentence": {
        "speaking": (1.4, "approved Repeat Sentence scoring example"),
        "listening": (1.5, "approved Repeat Sentence scoring example"),
    },
    "mc_single": {
        "reading": (1.0, "single-answer objective task"),
    },
    "mc_multiple": {
        "reading": (1.0, "negative-marked multiple-answer objective task"),
    },
    "l_mc_single": {
        "listening": (1.0, "single-answer objective task"),
    },
    "l_mc_multiple": {
        "listening": (1.0, "approved Listening MCQ Multiple scoring example"),
    },
    "highlight_correct_summary": {
        "listening": (1.0, "single-answer objective task"),
    },
    "select_missing_word": {
        "listening": (1.0, "single-answer objective task"),
    },
    "highlight_incorrect_words": {
        "reading": (5.5, "approved Highlight Incorrect Words scoring example"),
        "listening": (4.0, "approved Highlight Incorrect Words scoring example"),
    },
}


def fixed_subsection_skill_maxima(subsection_name):
    return {
        skill: maximum
        for skill, (maximum, _basis) in FIXED_TASK_MAXIMA.get(
            subsection_name, {}
        ).items()
    }


def question_skill_maximum_expectations(question):
    subsection = question.subsection
    if subsection is None:
        return ()

    fixed = FIXED_TASK_MAXIMA.get(subsection.name)
    if fixed:
        return tuple(
            SkillMaximumExpectation(skill, maximum, basis)
            for skill, (maximum, basis) in fixed.items()
        )

    structural = _structural_expectations(question, subsection.name)
    return tuple(structural)


def configured_question_skill_maxima(question):
    return {
        skill: getattr(question, f"{skill}_score_max")
        for skill in VALID_SKILLS
    }


def maximum_policy_rows(question):
    expectations = question_skill_maximum_expectations(question)
    configured = configured_question_skill_maxima(question)
    rows = []

    if not expectations:
        return [{
            "status": "review_required",
            "severity": "warning",
            "skill": "",
            "configured_maximum": _configured_summary(configured),
            "expected_maximum": "",
            "delta": "",
            "basis": "No authoritative task-specific maximum policy is approved.",
            "manual_action": (
                "Confirm the intended per-skill maxima with the rubric owner; "
                "do not enable v2 scoring for this task until approved."
            ),
        }]

    expected_skills = {expectation.skill for expectation in expectations}
    for expectation in expectations:
        current = configured[expectation.skill]
        status, severity, delta, action = _compare_maximum(
            current,
            expectation.maximum,
        )
        rows.append({
            "status": status,
            "severity": severity,
            "skill": expectation.skill,
            "configured_maximum": current if current is not None else "",
            "expected_maximum": expectation.maximum,
            "delta": delta,
            "basis": expectation.basis,
            "manual_action": action,
        })

    for skill, current in configured.items():
        if skill in expected_skills or current in (None, 0, 0.0):
            continue
        rows.append({
            "status": "unexpected_skill",
            "severity": "error",
            "skill": skill,
            "configured_maximum": current,
            "expected_maximum": 0.0,
            "delta": "",
            "basis": "The approved task policy does not award this skill.",
            "manual_action": (
                f"Clear Question.{skill}_score_max or obtain explicit policy approval."
            ),
        })

    return rows


def _structural_expectations(question, subsection_name):
    if subsection_name == "fib_dropdown":
        count = question.sub_questions.count()
        return _one("reading", count, "one reading point per configured blank")

    if subsection_name == "fib_drag_drop":
        count = question.options.filter(
            is_correct=True,
            order_position__isnull=False,
        ).count()
        return _one("reading", count, "one reading point per correct blank position")

    if subsection_name == "reorder_paragraphs":
        count = max(question.options.count() - 1, 0)
        return _one("reading", count, "one reading point per adjacent paragraph pair")

    if subsection_name == "l_fill_in_blanks":
        count = max(0, len(BLANK_RE.split(str(question.text or ""))) - 1)
        return _one("listening", count, "one listening point per visible blank")

    if subsection_name == "write_from_dictation":
        count = len(WORD_RE.findall(str(question.correct_answer or "")))
        if count <= 0:
            return ()
        return (
            SkillMaximumExpectation(
                "writing",
                float(count),
                "one writing point per word in the approved dictation transcript",
            ),
            SkillMaximumExpectation(
                "listening",
                1.0,
                "approved Write From Dictation scoring example",
            ),
        )

    return ()


def _one(skill, count, basis):
    if count <= 0:
        return ()
    return (SkillMaximumExpectation(skill, float(count), basis),)


def _compare_maximum(current, expected):
    if current is None:
        return (
            "missing",
            "error",
            "",
            f"Set the question maximum to {expected:g}.",
        )
    try:
        numeric = float(current)
    except (TypeError, ValueError):
        return (
            "invalid",
            "error",
            "",
            f"Replace the non-numeric maximum with {expected:g}.",
        )
    if not math.isfinite(numeric) or numeric <= 0:
        return (
            "invalid",
            "error",
            "",
            f"Replace the non-positive or non-finite maximum with {expected:g}.",
        )
    delta = numeric - expected
    if not math.isclose(numeric, expected, rel_tol=1e-9, abs_tol=1e-9):
        return (
            "mismatch",
            "error",
            delta,
            f"Review and set the question maximum to {expected:g}.",
        )
    return "match", "ok", 0.0, "No change required."


def _configured_summary(configured):
    return "; ".join(
        f"{skill}={value:g}"
        for skill, value in configured.items()
        if value not in (None, 0, 0.0)
    )
