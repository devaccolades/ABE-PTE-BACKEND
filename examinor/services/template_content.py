"""Evidence-checked, question-grounded assessment of unfamiliar template scripts."""

import math
import re

from django.conf import settings

from examinor.services.repetitive_answer import (
    ANSWER_TYPE_PROFILES, apply_answer_integrity_override,
)


VERSION = "template-content-v1"
WORD_RE = re.compile(r"[^\W_]+(?:['-][^\W_]+)?", re.UNICODE)
DEFAULT_CONFIG = {
    "enabled": True,
    "minimum_words": 25,
    "essay_minimum_words": 80,
    "minimum_generic_words": 20,
    "hard_ratio": 0.70,
    "minimum_confidence": 0.90,
}


def template_content_config():
    return {**DEFAULT_CONFIG, **getattr(settings, "TEMPLATE_CONTENT_CONFIG", {})}


def template_assessment_required(task_type, answer):
    config = template_content_config()
    minimum = config["essay_minimum_words"] if task_type == "write_essay" else config["minimum_words"]
    return (
        config["enabled"] and task_type in ANSWER_TYPE_PROFILES
        and len(WORD_RE.findall(answer)) >= minimum
    )


def template_assessment_instructions(task_type, answer):
    if not template_assessment_required(task_type, answer):
        return "", ""
    return """
TEMPLATE / QUESTION-SPECIFIC CONTENT CHECK (separate from rubric traits):
- Assess whether generic, reusable wording substitutes for answering THIS task.
  Do not claim you know whether the candidate memorized, copied or plagiarized it.
- A template may occur only once, or be paraphrased. Repetition is not required.
- Compare against the actual question, reference material, and attached image.
  Topic words, disconnected numbers and isolated keywords alone are not an answer.
- Describe Image needs meaningful image-specific observations/relationships;
  lecture/discussion summaries need accurately connected source ideas;
  Respond to a Situation needs the requested communication, audience and purpose;
  essays need a relevant position/reasoning/support, not interchangeable prose.
- Familiar introductions, conclusions, linking phrases, polite requests and
  speaker-attribution phrases are NOT by themselves evidence of invalidity.
  Meaningful task-specific claims and relevant reasoning must be listed under
  specific_points even when the surrounding language resembles a framework.
- Return template_assessment with verdict substantive, template_dominated, or
  uncertain. confidence is your confidence in this judgement (0 to 1), not a
  measured probability. addresses_task is a boolean. Use uncertain when unsure.
- generic_passages and specific_points contain objects with text and reason.
  text MUST be an exact, case-preserving contiguous quote from CANDIDATE_RESPONSE.
  Each generic quote must contain at least 4 words. Each specific quote must
  contain at least 2 words and express a relevant, meaningful idea, not keywords.
  Quote only the generic part, never an entire substantive answer indiscriminately.
  Do not overlap generic and specific quotes. Include a reason explaining each
  quote's relevance or lack of relevance to the supplied task/source.
- substantive requires addresses_task=true and at least one specific_point.
  template_dominated may have some specific_points; do not hide meaningful content.
- Keep template_assessment unchanged in language-only annotation audits.
- Keep normal rubric scores in scores. Application code applies any integrity
  override separately; do not replace rubric marks with an invented penalty.
""", ',\n  "template_assessment": {"verdict":"<substantive|template_dominated|uncertain>","confidence":0.0,"addresses_task":false,"generic_passages":[],"specific_points":[],"reason":"<task-grounded explanation>"}'


def validate_template_assessment(evaluation, task_type, answer):
    """Reject omitted or fabricated evidence before provider output is accepted."""
    if not template_assessment_required(task_type, answer):
        return True, None
    assessment = evaluation.get("template_assessment")
    if not isinstance(assessment, dict):
        return False, "Missing template_assessment for the descriptive answer."
    if assessment.get("verdict") not in {"substantive", "template_dominated", "uncertain"}:
        return False, "template_assessment has an invalid verdict."
    confidence = assessment.get("confidence")
    if (
        isinstance(confidence, bool) or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence) or not 0 <= confidence <= 1
    ):
        return False, "template_assessment confidence must be a finite number from 0 to 1."
    if not isinstance(assessment.get("addresses_task"), bool):
        return False, "template_assessment addresses_task must be boolean."
    if not isinstance(assessment.get("reason"), str) or not assessment["reason"].strip():
        return False, "template_assessment requires a task-grounded reason."
    positions = {}
    for key, minimum in (("generic_passages", 4), ("specific_points", 2)):
        quotes = assessment.get(key)
        if not isinstance(quotes, list) or len(quotes) > 30:
            return False, f"template_assessment {key} must be a list of at most 30 quotes."
        positions[key] = set()
        for quote in quotes:
            if not isinstance(quote, dict):
                return False, f"template_assessment {key} requires quote objects."
            text, reason = quote.get("text"), quote.get("reason")
            if (
                not isinstance(text, str) or len(WORD_RE.findall(text)) < minimum
                or text not in answer
                or not isinstance(reason, str) or not reason.strip()
            ):
                return False, f"template_assessment {key} requires exact candidate quotes and reasons."
            positions[key].update(_quoted_word_positions(answer, text))
    if positions["generic_passages"] & positions["specific_points"]:
        return False, "template_assessment generic and specific evidence overlaps."
    if assessment["verdict"] == "substantive" and (
        not assessment["addresses_task"] or not assessment["specific_points"]
    ):
        return False, "A substantive template_assessment must identify specific relevant content."
    return True, None


def inspect_template_content(evaluation, task_type, answer, *, source_available, context_complete=True):
    config = template_content_config()
    required = template_assessment_required(task_type, answer)
    result = {
        "detector_version": VERSION,
        "status": "not_applicable",
        "is_template_dominated": False,
        "requires_review": False,
        "reason": "Outside the configured semantic-template check scope or minimum length.",
    }
    if not required:
        return result
    valid, error = validate_template_assessment(evaluation, task_type, answer)
    if not valid:
        return {**result, "status": "unavailable", "requires_review": True, "reason": error}
    assessment = evaluation["template_assessment"]
    covered = set()
    for quote in assessment["generic_passages"]:
        covered.update(_quoted_word_positions(answer, quote["text"]))
    words = len(WORD_RE.findall(answer))
    ratio = len(covered) / words
    blocked = (
        source_available and context_complete
        and assessment["verdict"] == "template_dominated"
        and assessment["confidence"] >= config["minimum_confidence"]
        and not assessment["addresses_task"]
        and not assessment["specific_points"]
        and len(covered) >= config["minimum_generic_words"]
        and ratio >= config["hard_ratio"]
    )
    review = not blocked and (
        assessment["verdict"] != "substantive" or not source_available or not context_complete
    )
    return {
        **result,
        "status": "hard_zero" if blocked else "review" if review else "pass",
        "is_template_dominated": blocked,
        "requires_review": review,
        "word_count": words,
        "generic_word_count": len(covered),
        "generic_word_ratio": round(ratio, 4),
        "source_available": bool(source_available),
        "context_complete": context_complete,
        "assessment": assessment,
        "thresholds": config,
        "reason": (
            "Generic template wording dominates the answer without meaningful question-specific content."
            if blocked else assessment["reason"]
        ),
    }


def apply_template_content_override(result, detection):
    if detection["status"] == "not_applicable":
        return result
    result = apply_answer_integrity_override(
        result, detection, check_name="template_content",
        trigger_field="is_template_dominated", override_code="template_content_dominated",
    )
    if detection["is_template_dominated"]:
        feedback = result["evaluation"].get("feedback")
        if isinstance(feedback, dict):
            feedback["summary"] = detection["reason"]
        else:
            result["evaluation"]["feedback"] = {"summary": detection["reason"], "errors": []}
    return result


def _quoted_word_positions(answer, quote):
    positions = set()
    for match in re.finditer(re.escape(quote), answer):
        positions.update(
            index for index, word in enumerate(WORD_RE.finditer(answer))
            if word.start() >= match.start() and word.end() <= match.end()
        )
    return positions
