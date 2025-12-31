# examinor/api/views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from examinor.services.orchestrator import run_evaluation


@api_view(["POST"])
def evaluate_pte(request):
    """
    Simple endpoint to test the evaluation engine.
    Required BODY:
        {
            "subsection_name": "read_aloud",
            "question_text": "Your question...",
            "answer_text": "User response..."
        }
    """

    subsection_name = request.data.get("subsection_name")
    question_text = request.data.get("question_text")
    answer_text = request.data.get("answer_text")

    if not subsection_name or not question_text or not answer_text:
        return Response(
            {"error": "Missing required fields."},
            status=status.HTTP_400_BAD_REQUEST
        )
    evaluation_payload = {}

    if answer_text:
            evaluation_payload["answer_data"] = answer_text

    result = run_evaluation(
        subsection_name=subsection_name,
        question_text=question_text,
        evaluation_payload=evaluation_payload,
    )

    return Response(result, status=200)
