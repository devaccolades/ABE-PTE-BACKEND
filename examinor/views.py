# examinor/api/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from examinor.services.orchestrator import run_evaluation


@api_view(["POST"])
@permission_classes([IsAdminUser])
def evaluate_pte(request):
    """
    Simple endpoint to test the evaluation engine. Admin-only because every
    call is billed to the OpenAI account.
    Required BODY:
        {
            "subsection_name": "read_aloud",
            "question_text": "Your question...",
            "answer_text": "User response...",
            "audio_text": "Transcribed audio response...",
            "reference_answer": "Source transcript or reviewed key points...",
            "question_image": "data:image/png;base64,..."
        }
    """

    subsection_name = request.data.get("subsection_name")
    question_text = request.data.get("question_text")
    answer_text = request.data.get("answer_text")
    audio_text = request.data.get('audio_text')

    if not subsection_name or not question_text:
        return Response(
            {"error": "Missing required fields."},
            status=status.HTTP_400_BAD_REQUEST
        )
    evaluation_payload = {}

    if answer_text:
        evaluation_payload["answer_data"] = answer_text
    if audio_text:
        evaluation_payload["transcribed_audio_data"] = (
            {"transcription": {"text": audio_text}}
            if isinstance(audio_text, str)
            else audio_text
        )
    if "reference_answer" in request.data:
        evaluation_payload["reference_answer"] = request.data["reference_answer"]
    if "question_image" in request.data:
        evaluation_payload["question_image"] = request.data["question_image"]

    result = run_evaluation(
        subsection_name=subsection_name,
        question_text=question_text,
        evaluation_payload=evaluation_payload,
    )

    response_status = status.HTTP_200_OK
    if result.get("retryable") is False and not result.get("ok"):
        response_status = status.HTTP_400_BAD_REQUEST
    return Response(result, status=response_status)
