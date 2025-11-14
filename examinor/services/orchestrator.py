# examinor/services/orchestrator.py

from .evaluator import evaluate_with_openai


def run_evaluation(task_type: str, question_text: str, answer_text: str, rubric: dict):
    """
    A small orchestrator that:
    1. Receives raw inputs
    2. Calls evaluator
    3. Returns AI evaluation result
    """

    result = evaluate_with_openai(task_type, question_text, answer_text, rubric)

    if not result["success"]:
        return {
            "ok": False,
            "error": result["error"],
            "prompt_hash": result["prompt_hash"],
            "raw": result["raw"],
        }

    return {
        "ok": True,
        "prompt_hash": result["prompt_hash"],
        "evaluation": result["data"],
    }
