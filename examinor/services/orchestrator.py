import hashlib
import json

from django.conf import settings
from django.db import IntegrityError

from mocktest.models import SubSection
from mocktest.models import GlobalRubric
from examinor.scoring.validators import (
    validate_and_normalize_evaluation_result,
    validate_and_normalize_language_feedback,
)
from examinor.services.prompt_builder import build_prompt, evaluation_answer_text
from examinor.services.evaluator import evaluate_with_openai
from examinor.models import EvaluationCache


LANGUAGE_ANNOTATION_TASKS = frozenset({
    "summarize_written_text",
    "write_essay",
    "summarize_spoken_text",
})


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

    if (
        subsection.name == "summarize_spoken_text"
        and not evaluation_payload.get("reference_answer")
    ):
        return {
            "ok": False,
            "error": (
                "Summarize Spoken Text requires a reference transcript, "
                "model answer, or key points in question.correct_answer."
            ),
        }

    rubric = build_task_rubric(subsection)
    prompt, p_hash = build_prompt(
        task_type=subsection.name,
        question_text=question_text,
        evaluation_payload=evaluation_payload,
        rubric=rubric
    )

    cache_model = settings.OPENAI_EVALUATION_MODEL
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
            return {
                "ok": True,
                "prompt_hash": p_hash,
                "model": cache_model,
                "evaluation": normalized,
                "cached": True
            }
        cached.delete()

    result = evaluate_with_openai(
        prompt,
        p_hash
    )

    if not result["success"]:
        return {
            "ok": False,
            "error": result["error"],
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
    )
    needs_language_audit = (
        subsection.name in LANGUAGE_ANNOTATION_TASKS
        and (
            not valid
            or _has_reduced_language_score(normalized)
        )
    )
    if needs_language_audit:
        audit_reason = validation_error or (
            "Grammar or spelling is below its maximum. Perform a final "
            "completeness audit and include every clear error."
        )
        repair_prompt = (
            f"{prompt}\n\n"
            "FINAL LANGUAGE-ANNOTATION AUDIT:\n"
            f"{audit_reason}\n"
            "PREVIOUS_OUTPUT:\n"
            f"{json.dumps(result['data'], ensure_ascii=False, separators=(',', ':'))}\n"
            "Return the complete corrected JSON response. Re-check every sentence "
            "and ensure every error.text is copied exactly from CANDIDATE_RESPONSE."
        )
        repair_hash = hashlib.sha256(repair_prompt.encode()).hexdigest()
        result = evaluate_with_openai(repair_prompt, repair_hash)
        if result["success"]:
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
            "prompt_hash": p_hash,
            "model": cache_model,
            "prompt": prompt,
            "raw": result.get("raw"),
        }

    if not valid:
        return {
            "ok": False,
            "error": f"Evaluation output failed validation: {validation_error}",
            "prompt_hash": p_hash,
            "model": cache_model,
            "raw": result.get("raw"),
        }

    normalized = save_evaluation_cache(
        p_hash,
        cache_model,
        normalized,
    )

    return {
        "ok": True,
        "prompt_hash": p_hash,
        "model": cache_model,
        "evaluation": normalized,
    }


def _validate_provider_evaluation(data, rubric, task_type, answer_text):
    valid, normalized, error = validate_and_normalize_evaluation_result(
        {"ok": True, "evaluation": data},
        rubric,
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
        )
        if not valid:
            return False, None, error

    return True, normalized["evaluation"], None


def _has_reduced_language_score(evaluation):
    if not isinstance(evaluation, dict):
        return False
    scores = evaluation.get("scores")
    if not isinstance(scores, dict):
        return False
    for key in ("grammar", "spelling"):
        payload = scores.get(key)
        if not isinstance(payload, dict):
            continue
        score = float(payload.get("score") or 0)
        maximum = float(payload.get("max", payload.get("maximum")) or 0)
        if score < maximum:
            return True
    return False
