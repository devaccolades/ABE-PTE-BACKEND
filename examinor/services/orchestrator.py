from django.conf import settings
from django.db import IntegrityError

from mocktest.models import SubSection
from mocktest.models import GlobalRubric
from examinor.services.prompt_builder import build_prompt
from examinor.services.evaluator import evaluate_with_openai
from examinor.models import EvaluationCache


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
        return {
            "ok": True,
            "prompt_hash": p_hash,
            "model": cache_model,
            "evaluation": cached.result,
            "cached": True
        }

    result = evaluate_with_openai(
        prompt,
        p_hash 
    )
    if result["success"]:
        result["data"] = save_evaluation_cache(
            p_hash,
            cache_model,
            result["data"],
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

    return {
        "ok": True,
        "prompt_hash": p_hash,
        "model": cache_model,
        "evaluation": result["data"],
    }
