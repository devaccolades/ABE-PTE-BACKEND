import hashlib
import json
from copy import deepcopy

from django.conf import settings
from django.db import IntegrityError

from mocktest.models import SubSection
from mocktest.models import GlobalRubric
from examinor.scoring.validators import (
    rubric_maxima,
    validate_and_normalize_evaluation_result,
    validate_and_normalize_language_feedback,
)
from examinor.services.prompt_builder import (
    PROMPT_VERSION,
    MAX_CANDIDATE_RESPONSE_CHARS, MAX_REFERENCE_MATERIAL_CHARS,
    build_prompt, evaluation_answer_text, normalize_answer_text,
)
from examinor.services.evaluator import evaluate_with_openai
from examinor.services.evaluation_context import (
    EvaluationContextError,
    validate_evaluation_context,
)
from examinor.services.speech_score_guardrails import apply_speech_score_guardrails
from examinor.services.prompt_copy import detect_prompt_copy, apply_prompt_copy_override
from examinor.services.strict_form import (
    inspect_strict_form, apply_strict_form_override, apply_strict_form_policy,
)
from examinor.services.template_content import (
    apply_template_content_override, inspect_template_content, validate_template_assessment,
)
from examinor.models import EvaluationCache
from examinor.services.source_fidelity import (
    audit_source_fidelity, apply_source_fidelity_override,
)


LANGUAGE_ANNOTATION_TASKS = frozenset({
    "summarize_written_text",
    "write_essay",
    "summarize_spoken_text",
})

PROVIDER_OUTPUT_VALIDATION_ERROR_CODE = "provider_output_validation_failed"


def build_task_rubric(subsection: SubSection) -> dict:
    """
    Merges subsection rubric with required global rubrics.
    Result structure is always:
      {
        "criterion_id": { "max": X, ... },
        ...
      }
    """

    final_rubric = dict(subsection.rubric or {})

    # add global pronunciation rubric if enabled
    if getattr(subsection, "use_pronunciation", False):
        gr = GlobalRubric.objects.filter(key="pronunciation").first()
        if gr:
            final_rubric["pronunciation"] = gr.rubric

    # add global oral fluency rubric if enabled
    if getattr(subsection, "use_fluency", False):
        gr = GlobalRubric.objects.filter(key="oral_fluency").first()
        if gr:
            final_rubric["oral_fluency"] = gr.rubric

    return final_rubric


def save_evaluation_cache(prompt_hash, model, result):
    try:
        EvaluationCache.objects.create(
            prompt_hash=prompt_hash,
            model=model,
            result=result,
        )
        return result
    except IntegrityError:
        cached = EvaluationCache.objects.filter(
            prompt_hash=prompt_hash,
            model=model,
        ).first()
        return cached.result if cached else result


def  run_evaluation(
    subsection_name: str,
    question_text: str,
    evaluation_payload: dict,
):
    """
    MAIN PTE evaluation orchestrator.

    ✔ Always receives TEXT ANSWER (raw typed or transcription)
    ✔ Fetches rubrics from DB (subsection + global traits)
    ✔ Builds deterministic nano-friendly prompt
    ✔ Sends to evaluator (GPT)
    ✔ Returns structured scoring response

    Does NOT handle:
      - Transcription (done earlier)
      - Audio processing
      - Question audio/image conversion
    """

    matching_subsections = SubSection.objects.filter(name=subsection_name)
    count = matching_subsections.count()

    if count == 0:
        return {
            "ok": False,
            "error": f"Invalid subsection '{subsection_name}'",
            "evaluation": None
        }

    if count > 1:
        return {
            "ok": False,
            "error": f"Duplicate subsection name '{subsection_name}'. Evaluate by linked subsection.",
            "evaluation": None,
        }

    return run_evaluation_for_subsection(
        matching_subsections.first(),
        question_text,
        evaluation_payload,
    )


def run_evaluation_for_subsection(
    subsection: SubSection,
    question_text: str,
    evaluation_payload: dict,
):
    """
    Evaluate using the exact subsection linked to a question.
    This avoids duplicate-name failures when question banks contain repeated
    SubSection rows with the same choice value.
    """

    try:
        evaluation_payload, input_context = validate_evaluation_context(
            subsection.name, evaluation_payload,
        )
    except EvaluationContextError as exc:
        return exc.as_result()

    rubric = build_task_rubric(subsection)
    prompt, p_hash = build_prompt(
        task_type=subsection.name,
        question_text=question_text,
        evaluation_payload=evaluation_payload,
        rubric=rubric
    )

    cache_model = settings.OPENAI_EVALUATION_MODEL
    strict_form = inspect_strict_form(evaluation_answer_text(evaluation_payload), subsection.name)
    if strict_form["is_invalid"]:
        return apply_strict_form_override(
            _zero_policy_result(rubric, p_hash, cache_model, input_context, strict_form["reason"]),
            strict_form,
        )
    prompt_copy = detect_prompt_copy(
        evaluation_answer_text(evaluation_payload), question_text, subsection.name,
    )
    if prompt_copy["is_prompt_copy"]:
        return apply_prompt_copy_override(
            _zero_policy_result(rubric, p_hash, cache_model, input_context, prompt_copy["reason"]),
            prompt_copy,
        )

    cached = EvaluationCache.objects.filter(
        prompt_hash=p_hash,
        model=cache_model,
    ).first()
    if cached:
        valid, normalized, _ = _validate_provider_evaluation(
            cached.result,
            rubric,
            subsection.name,
            evaluation_answer_text(evaluation_payload),
        )
        if valid:
            normalized = apply_speech_score_guardrails(
                normalized,
                task_type=subsection.name,
                question_text=question_text,
                evaluation_payload=evaluation_payload,
            )
            return _apply_template_policy({
                "ok": True,
                "prompt_hash": p_hash,
                "model": cache_model,
                "evaluation": normalized,
                "input_context": input_context,
                "cached": True
            }, subsection.name, question_text, evaluation_payload)
        cached.delete()

    result = _evaluate_with_context(
        prompt,
        p_hash,
        evaluation_payload,
    )

    if not result["success"]:
        return {
            "ok": False,
            "error": result["error"],
            "retryable": result.get("retryable"),
            "prompt_hash": p_hash,
            "model": cache_model,
            "prompt": prompt,
            "raw": result.get("raw")
        }

    valid, normalized, validation_error = _validate_provider_evaluation(
        result["data"],
        rubric,
        subsection.name,
        evaluation_answer_text(evaluation_payload),
        strict_evidence=True,
    )
    template_valid, _ = validate_template_assessment(
        result["data"], subsection.name, evaluation_answer_text(evaluation_payload), strict=True,
    ) if isinstance(result["data"], dict) else (False, None)
    initial_template_assessment = (
        deepcopy(result["data"].get("template_assessment")) if template_valid else None
    )
    initial_normalized = normalized if valid else None
    if initial_normalized is None:
        scores_valid, score_result, _ = validate_and_normalize_evaluation_result(
            {"ok": True, "evaluation": result["data"]}, rubric,
        )
        if scores_valid:
            # Invalid language annotations must not discard valid content/form scores.
            initial_normalized = score_result["evaluation"]
    needs_language_audit = (
        subsection.name in LANGUAGE_ANNOTATION_TASKS
        and (not valid or _has_language_scores(normalized))
    )
    if needs_language_audit:
        audit_reason = validation_error or (
            "Perform a final sentence-by-sentence completeness audit and include "
            "every clear grammar and spelling error, including rare errors allowed "
            "by the highest grammar band."
        )
        repair_prompt = (
            f"{prompt}\n\n"
            "FINAL LANGUAGE-ANNOTATION AUDIT:\n"
            f"{audit_reason}\n"
            "PREVIOUS_OUTPUT:\n"
            f"{json.dumps(result['data'], ensure_ascii=False, separators=(',', ':'))}\n"
            "Keep every non-grammar and non-spelling score exactly as shown in "
            "PREVIOUS_OUTPUT. Return the complete corrected JSON response and ensure "
            "every error.text is copied exactly from CANDIDATE_RESPONSE."
        )
        repair_hash = hashlib.sha256(repair_prompt.encode()).hexdigest()
        result = _evaluate_with_context(repair_prompt, repair_hash, evaluation_payload)
        if result["success"]:
            _restore_template_assessment(result["data"], initial_template_assessment)
            result["data"] = _preserve_non_language_scores(
                result["data"],
                initial_normalized,
            )
            valid, normalized, validation_error = _validate_provider_evaluation(
                result["data"],
                rubric,
                subsection.name,
                evaluation_answer_text(evaluation_payload),
                strict_evidence=True,
            )

    if result["success"] and not valid:
        previous_output = result["data"]
        repair_prompt = _rubric_validation_repair_prompt(
            prompt,
            previous_output,
            validation_error,
            rubric,
        )
        repair_hash = hashlib.sha256(repair_prompt.encode()).hexdigest()
        result = _evaluate_with_context(repair_prompt, repair_hash, evaluation_payload)
        if result["success"]:
            _restore_template_assessment(result["data"], initial_template_assessment)
            scores_valid, _, _ = validate_and_normalize_evaluation_result(
                {"ok": True, "evaluation": previous_output}, rubric,
            )
            if scores_valid and subsection.name in LANGUAGE_ANNOTATION_TASKS:
                result["data"] = _preserve_non_language_scores(
                    result["data"], previous_output,
                )
            else:
                result["data"] = _preserve_valid_scores(
                    result["data"], previous_output, rubric,
                )
            valid, normalized, validation_error = _validate_provider_evaluation(
                result["data"],
                rubric,
                subsection.name,
                evaluation_answer_text(evaluation_payload),
            )

    if not result["success"]:
        return {
            "ok": False,
            "error": result["error"],
            "retryable": result.get("retryable"),
            "prompt_hash": p_hash,
            "model": cache_model,
            "prompt": prompt,
            "raw": result.get("raw"),
        }

    if not valid:
        return {
            "ok": False,
            "error": f"Evaluation output failed validation: {validation_error}",
            "code": PROVIDER_OUTPUT_VALIDATION_ERROR_CODE,
            "retryable": True,
            "prompt_hash": p_hash,
            "model": cache_model,
            "raw": result.get("raw"),
        }

    normalized = apply_speech_score_guardrails(
        normalized,
        task_type=subsection.name,
        question_text=question_text,
        evaluation_payload=evaluation_payload,
    )
    normalized = save_evaluation_cache(
        p_hash,
        cache_model,
        normalized,
    )
    normalized = apply_speech_score_guardrails(
        normalized,
        task_type=subsection.name,
        question_text=question_text,
        evaluation_payload=evaluation_payload,
    )

    return _apply_template_policy({
        "ok": True,
        "prompt_hash": p_hash,
        "model": cache_model,
        "evaluation": normalized,
        "input_context": input_context,
    }, subsection.name, question_text, evaluation_payload)


def _restore_template_assessment(candidate, assessment):
    if isinstance(candidate, dict) and assessment is not None:
        candidate["template_assessment"] = deepcopy(assessment)


def _zero_policy_result(rubric, prompt_hash, model, context, reason):
    maxima = rubric_maxima(rubric)
    return {
        "ok": True, "prompt_hash": prompt_hash, "model": model, "prompt_version": PROMPT_VERSION,
        "provider_called": False, "input_context": context,
        "evaluation": {
            "scores": {trait: {"score": 0.0, "max": maximum} for trait, maximum in maxima.items()},
            "weighted_score": 0.0, "max_score": sum(maxima.values()),
            "feedback": {"summary": reason, "errors": []},
        },
    }


def _apply_template_policy(result, task_type, question_text, payload):
    result["prompt_version"] = PROMPT_VERSION
    answer = evaluation_answer_text(payload)
    reference = normalize_answer_text(payload.get("reference_answer"))
    if task_type == "describe_image":
        source_available = bool(payload.get("question_image"))
    elif task_type in {"retell_lecture", "summarise_group_discussion", "summarize_spoken_text"}:
        source_available = bool(reference.strip())
    else:
        source_available = bool(str(question_text or "").strip())
    detection = inspect_template_content(
        result["evaluation"], task_type, answer,
        source_available=source_available,
        context_complete=(
            len(answer) <= MAX_CANDIDATE_RESPONSE_CHARS
            and len(reference) <= MAX_REFERENCE_MATERIAL_CHARS
        ),
    )
    result = apply_template_content_override(result, detection)
    if _has_applied_override(result):
        return apply_strict_form_policy(result, task_type, answer)
    # Meaning is reviewed before Form so an off-topic or contradictory summary is
    # zeroed for that reason, not for the Form mark the grader gave it.
    source = str(question_text or "") if task_type == "summarize_written_text" else reference
    fidelity = audit_source_fidelity(task_type, answer, source)
    if fidelity["status"] == "unavailable":
        formed = apply_strict_form_policy(result, task_type, answer)
        if _has_applied_override(formed):
            # An existing integrity zero must not become a provider error or lose its reason.
            formed["integrity_checks"]["source_fidelity"] = fidelity
            return formed
        return {
            "ok": False, "code": "source_fidelity_unavailable",
            "error": fidelity["reason"], "retryable": fidelity["retryable"],
            "model": result["model"], "prompt_hash": result["prompt_hash"], "prompt_version": PROMPT_VERSION,
            "input_context": result.get("input_context"),
            "integrity_checks": {**result.get("integrity_checks", {}), "source_fidelity": fidelity},
        }
    result = apply_source_fidelity_override(result, fidelity)
    if _has_applied_override(result):
        return result
    return apply_strict_form_policy(result, task_type, answer)


def _has_applied_override(result):
    return any(item.get("applied") for item in result.get("score_overrides", []) if isinstance(item, dict))


def _evaluate_with_context(prompt, prompt_hash, payload):
    image = payload.get("question_image")
    if image:
        return evaluate_with_openai(prompt, prompt_hash, image_data_url=image["data_url"])
    return evaluate_with_openai(prompt, prompt_hash)


def _validate_provider_evaluation(data, rubric, task_type, answer_text, *, strict_evidence=False):
    # strict_evidence before a repair request, so unusable template evidence and
    # language annotations can be repaired; after it, they are dropped or recorded
    # instead of failing the answer.
    valid, normalized, error = validate_and_normalize_evaluation_result(
        {"ok": True, "evaluation": data},
        rubric,
    )
    if not valid:
        return False, None, error

    valid, error = validate_template_assessment(
        normalized["evaluation"], task_type, answer_text, strict=strict_evidence,
    )
    if not valid:
        return False, None, error

    score_keys = normalized["evaluation"].get("scores", {})
    if (
        task_type in LANGUAGE_ANNOTATION_TASKS
        and {"grammar", "spelling"} & set(score_keys)
    ):
        valid, normalized, error = validate_and_normalize_language_feedback(
            normalized,
            answer_text,
            strict=strict_evidence,
        )
        if not valid:
            return False, None, error

    return True, normalized["evaluation"], None


def _has_language_scores(evaluation):
    if not isinstance(evaluation, dict):
        return False
    scores = evaluation.get("scores")
    if not isinstance(scores, dict):
        return False
    return any(
        isinstance(scores.get(key), dict)
        for key in ("grammar", "spelling")
    )


def _preserve_non_language_scores(candidate, initial):
    if not isinstance(candidate, dict) or not isinstance(initial, dict):
        return candidate
    initial_scores = initial.get("scores")
    candidate_scores = candidate.get("scores")
    if not isinstance(initial_scores, dict) or not isinstance(candidate_scores, dict):
        return candidate

    preserved = deepcopy(candidate)
    preserved_scores = dict(preserved["scores"])
    for key, payload in initial_scores.items():
        if key not in {"grammar", "spelling"}:
            preserved_scores[key] = deepcopy(payload)
    preserved["scores"] = preserved_scores
    return preserved


def _rubric_validation_repair_prompt(prompt, previous, validation_error, rubric):
    allowed_ranges = {
        key: {"min": 0, "max": maximum}
        for key, maximum in rubric_maxima(rubric).items()
    }
    return (
        f"{prompt}\n\n"
        "FINAL RUBRIC VALIDATION REPAIR:\n"
        f"The previous output failed validation: {validation_error}\n"
        "ALLOWED_SCORE_RANGES:\n"
        f"{json.dumps(allowed_ranges, ensure_ascii=False, separators=(',', ':'))}\n"
        "PREVIOUS_OUTPUT:\n"
        f"{json.dumps(previous, ensure_ascii=False, separators=(',', ':'))}\n"
        "Return the complete corrected JSON object. Keep every already-valid "
        "criterion score and all valid feedback unchanged. Rescore only invalid "
        "criteria using their supplied rubric bands. Every score must be within "
        "its allowed range, every max must equal the allowed max, and weighted_score "
        "and max_score must be recalculated. Return JSON only."
    )


def _preserve_valid_scores(candidate, previous, rubric):
    if not isinstance(candidate, dict) or not isinstance(previous, dict):
        return candidate
    candidate_scores = candidate.get("scores")
    previous_scores = previous.get("scores")
    if not isinstance(candidate_scores, dict) or not isinstance(previous_scores, dict):
        return candidate

    maxima = rubric_maxima(rubric)
    preserved = deepcopy(candidate)
    preserved_scores = dict(candidate_scores)
    for key, maximum in maxima.items():
        payload = previous_scores.get(key)
        if (
            not isinstance(payload, dict)
            or "score" not in payload
            or "max" not in payload
        ):
            continue
        try:
            score = float(payload["score"])
            declared_maximum = float(payload["max"])
        except (TypeError, ValueError):
            continue
        if declared_maximum == maximum and 0 <= score <= maximum:
            preserved_scores[key] = deepcopy(payload)
    preserved["scores"] = preserved_scores
    return preserved
