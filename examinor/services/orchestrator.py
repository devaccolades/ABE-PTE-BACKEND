# examinor/services/orchestrator.py

from django.http import JsonResponse
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

    final_rubric = subsection.rubric or {}

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


def run_evaluation(
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

    # --- Step 1: Load subsection ---
    try:
        subsection = SubSection.objects.get(name=subsection_name)
    except SubSection.DoesNotExist:
        return {
            "ok": False,
            "error": f"Invalid subsection '{subsection_name}'",
            "evaluation": None
        }
    # return subsection.name
    # --- Step 2: Build complete rubric ---
    rubric = build_task_rubric(subsection)
    # --- Step 3: Build prompt ---
    prompt, p_hash = build_prompt(
        task_type=subsection.name,
        question_text=question_text,
        evaluation_payload=evaluation_payload,
        rubric=rubric
    )

    # NEW: Cache check
    cached = EvaluationCache.objects.filter(prompt_hash=p_hash).first()
    if cached:
        return {
            "ok": True,
            "prompt_hash": p_hash,
            # "rubric_used": rubric,
            "evaluation": cached.result,
            # "raw": None,
            "cached": True
        }


    # --- Step 4: Evaluate with GPT ---
    result = evaluate_with_openai(
        task_type=subsection.name,
        question_text=question_text,
        evaluation_payload=evaluation_payload,
        rubric=rubric
    )
    if result["success"]:
        EvaluationCache.objects.create(
            prompt_hash=p_hash,
            result=result["data"]
        )

    if not result["success"]:
        return {
            "ok": False,
            "error": result["error"],
            "prompt_hash": p_hash,
            "prompt": prompt,
            "raw": result.get("raw")
        }

    # --- Step 5: Return combined response ---
    return {
        "ok": True,
        "prompt_hash": p_hash,
        # "rubric_used": rubric,
        "evaluation": result["data"],
        # "raw": result["raw"],
    }
