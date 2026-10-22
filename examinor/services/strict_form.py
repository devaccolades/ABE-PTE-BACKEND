"""Company policy: full Form eligibility or zero for the complete answer."""

import unicodedata

from django.conf import settings
import pysbd

from examinor.services.repetitive_answer import apply_answer_integrity_override


WORD_LIMITS = {
    "summarize_spoken_text": (50, 70),
    "summarize_written_text": (5, 75),
    "write_essay": (200, 300),
}


def inspect_strict_form(answer, task_type, evaluation=None):
    enabled = getattr(settings, "STRICT_FORM_POLICY_ENABLED", True)
    applicable = enabled and task_type in WORD_LIMITS
    result = {
        "detector_version": "company-strict-form-v1",
        "policy_source": "company",
        "enabled": enabled,
        "applicable": applicable,
        "is_invalid": False,
        "reason": "Strict Form policy is not applicable.",
    }
    if not applicable:
        return result
    text = unicodedata.normalize("NFKC", str(answer or "")).strip()
    count = sum(any(character.isalnum() for character in token) for token in text.split())
    minimum, maximum = WORD_LIMITS[task_type]
    violations = []
    if not minimum <= count <= maximum:
        violations.append("word_count_outside_full_credit_range")
    sentence_count = None
    if task_type == "summarize_written_text":
        sentence_count = len(pysbd.Segmenter(language="en", clean=False).segment(text))
        if sentence_count != 1:
            violations.append("not_one_sentence")
    form = evaluation.get("scores", {}).get("form") if isinstance(evaluation, dict) else None
    if isinstance(form, dict):
        score = float(form.get("score") or 0)
        form_maximum = float(form.get("max", form.get("maximum")) or 0)
        if form_maximum <= 0 or score != form_maximum:
            violations.append("form_credit_below_maximum")
    if violations:
        details = f"Company policy requires {minimum}-{maximum} words; this answer contains {count}."
        if "not_one_sentence" in violations:
            details += f" A written summary must be one sentence; detected {sentence_count}."
        if "form_credit_below_maximum" in violations:
            details += " The assessed Form score is below full credit."
        reason = f"{details} The whole answer receives zero under the company strict Form policy."
    else:
        reason = "The answer meets the company strict Form checks performed so far."
    return {
        **result,
        "is_invalid": bool(violations),
        "word_count": count,
        "minimum_words": minimum,
        "maximum_words": maximum,
        "sentence_count": sentence_count,
        "assessed_form": form,
        "violations": violations,
        "reason": reason,
    }


def apply_strict_form_override(result, detection):
    if not detection["applicable"]:
        return result
    result = apply_answer_integrity_override(
        result, detection, check_name="strict_form", trigger_field="is_invalid",
        override_code="company_strict_form",
    )
    if detection["is_invalid"]:
        feedback = result["evaluation"].get("feedback")
        if isinstance(feedback, dict):
            feedback["summary"] = detection["reason"]
        else:
            result["evaluation"]["feedback"] = {"summary": detection["reason"], "errors": []}
    return result


def apply_strict_form_policy(result, task_type, answer):
    evaluation = result.get("evaluation")
    if result.get("provider_called") is False:
        evaluation = None
    else:
        # Another gate may already have zeroed Form. Inspect the original marks
        # so a template/repetition zero is not falsely blamed on Form eligibility.
        for override in result.get("score_overrides") or []:
            if isinstance(override, dict) and isinstance(override.get("original_scores"), dict):
                evaluation = {"scores": override["original_scores"]}
                break
    return apply_strict_form_override(result, inspect_strict_form(answer, task_type, evaluation))


def strict_form_instructions(task_type, answer):
    detection = inspect_strict_form(answer, task_type)
    if not detection["applicable"]:
        return ""
    return (
        "COMPANY STRICT FORM POLICY (overrides partial-credit Form bands):\n"
        f"- The backend counted {detection['word_count']} words. The inclusive full-credit "
        f"range is {detection['minimum_words']}-{detection['maximum_words']}. "
        "Use this count; do not estimate a different word count.\n"
        "- Form may receive its rubric maximum only when ALL Form requirements "
        "are met; otherwise score Form zero. Do not use an intermediate Form band.\n"
        "- For Summarize Written Text, verify it is one complete sentence; "
        "sentence-boundary detection alone does not prove grammatical completeness.\n"
        "- Grade the other criteria normally. Backend policy separately zeros "
        "the whole answer if full Form eligibility fails.\n"
    )
