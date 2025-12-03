import os
from celery import shared_task
from .models import *
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from mocktest.services.transcription import transcribe_and_analyse
from examinor.services.orchestrator import run_evaluation


# @shared_task
# def transcribe_task(user_response_id,temp_path):
#     print("running whisper transcription")

#     transcription = transcribe_and_analyse(temp_path)
#     object = UserResponse.objects.get(id=user_response_id)
#     object.transcribed_audio_data=transcription
#     object.save()
#     return {"user_response_id": user_response_id, "transcription": transcription}


# @shared_task
# def evaluate_user_response(user_answer_id, question_id):
#     print("evaluations begins")
#     user_answer = UserResponse.objects.get(id=user_answer_id)
#     question = Question.objects.get(id=question_id)
#     subsection = question.subsection.name
#     evaluate = run_evaluation(subsection,question.text,user_answer.answer_data)
#     user_answer.evaluation_result=evaluate
#     user_answer.save()
#     return {"user response with evaluation"}

@shared_task
def transcribe_task(user_response_id, temp_path):
    print("Running Whisper transcription...")

    try:
        if not os.path.exists(temp_path):
            return {
                "error": "Audio file not found",
                "details": f"Path '{temp_path}' does not exist",
                "user_response_id": user_response_id
            }

        try:
            transcription = transcribe_and_analyse(temp_path)
        except Exception as e:
            return {
                "error": "Failed to transcribe audio",
                "details": str(e),
                "user_response_id": user_response_id
            }

        try:
            user_response = UserResponse.objects.get(id=user_response_id)
        except UserResponse.DoesNotExist:
            return {
                "error": "UserResponse not found",
                "user_response_id": user_response_id
            }

        try:
            user_response.transcribed_audio_data = transcription
            user_response.save()
        except DatabaseError as db_err:
            return {
                "error": "Failed to save transcription",
                "details": str(db_err),
                "user_response_id": user_response_id
            }

        return {
            "status": "success",
            "user_response_id": user_response_id,
            "transcribed_audio": transcription,
        }

    except Exception as e:
        return {
            "error": "Unexpected error occurred during transcription",
            "details": str(e),
            "user_response_id": user_response_id
        }


@shared_task
def evaluate_user_response(user_answer_id, question_id):
    print("Evaluation begins...")

    try:
        try:
            user_answer = UserResponse.objects.get(id=user_answer_id)
        except UserResponse.DoesNotExist:
            return {"error": f"UserResponse {user_answer_id} does not exist"}

        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return {"error": f"Question {question_id} does not exist"}

        if not question.subsection:
            return {"error": f"Question {question_id} has no subsection assigned"}

        subsection = question.subsection.name

        if not user_answer.answer_data:
            return {"error": "No answer_data provided to evaluate"}

        try:
            evaluation_result = run_evaluation(
                subsection,
                question.text,
                user_answer.answer_data
            )
        except Exception as e:
            return {"error": "Error during evaluation", "details": str(e)}

        try:
            user_answer.evaluation_result = evaluation_result
            user_answer.save()
        except DatabaseError as db_err:
            return {"error": "Failed to save evaluation result", "details": str(db_err)}

        return {
            "status": "success",
            "user_answer_id": user_answer_id,
            "question_id": question_id,
            "subsection": subsection,
            "evaluation_result": evaluation_result,
        }

    except Exception as e:
        return {"error": "Unexpected error occurred", "details": str(e)}
    