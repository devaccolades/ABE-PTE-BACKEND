from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from examinor.services.rubric_store import RUBRICS
from examinor.services.evaluator import evaluate_with_openai


class TestManualEvaluationAPIView(APIView):
    """
    POST /examinor/test/
    {
        "task_type": "write_essay",
        "question": "Write an essay about ...",
        "answer": "The essay is about ..."
    }
    """
    def post(self, request, *args, **kwargs):
        task_type = request.data.get("task_type")
        question_text = request.data.get("question")
        answer_text = request.data.get("answer", "")

        # --- Validate ---
        if not task_type:
            return Response({"error": "task_type is required"}, status=400)

        if task_type not in RUBRICS:
            return Response(
                {"error": f"Unknown task_type '{task_type}'. Not found in rubric store."},
                status=400
            )

        if not question_text:
            return Response({"error": "question text is required"}, status=400)

        # --- Get rubric from memory ---
        rubric = RUBRICS[task_type]

        # --- Call evaluator ---
        result = evaluate_with_openai(task_type, question_text, answer_text, rubric)

        # Return as-is
        return Response(result, status=200 if result["success"] else 500)
