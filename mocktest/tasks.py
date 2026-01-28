import os
import uuid
import subprocess
from celery import shared_task

from examinor.services.rule_evaluator import run_rule_evaluation
from .models import *
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from mocktest.services.transcription import transcribe_and_analyse
from examinor.services.orchestrator import run_evaluation


    # print("Running Whisper transcription...")

    # if not os.path.exists(input_path):
    #     return {"error": "Audio file not found", "path": input_path}
    # try:
    #     subprocess.run(
    #         [
    #             "ffmpeg", "-y",
    #             "-i", input_path,
    #             "-ar", "16000",
    #             "-ac", "1",
    #             output_path
    #         ],
    #         check=True,
    #         stdout=subprocess.DEVNULL,
    #         stderr=subprocess.DEVNULL
    #     )
    # except Exception as e:
    #     return {
    #         "error": "FFmpeg conversion failed",
    #         "details": str(e)
    #     }

    # try:
    #     transcription = transcribe_and_analyse(output_path)
    # except Exception as e:
    #     return {
    #         "error": "Failed to transcribe audio",
    #         "details": str(e)
    #     }

    # user_response = UserResponse.objects.get(id=user_response_id)
    # user_response.transcribed_audio_data = transcription
    # user_response.save()

    # # cleanup
    # os.remove(input_path)
    # os.remove(output_path)

    # return {"status": "success", "transcription": transcription}
@shared_task(bind=True)
def transcribe_task(self,user_response_id,):
    user_response = UserResponse.objects.get(id=user_response_id)

    input_path = user_response.answer_audio.path
    output_path = f"/tmp/{uuid.uuid4()}.wav"

    # Convert audio to wav
    subprocess.run([
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        output_path
    ], check=True)

    transcript = transcribe_and_analyse(output_path)

    user_response.transcribed_audio_data = transcript
    user_response.save()

    os.remove(output_path)

    return user_response_id

from django.db import transaction

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
        
        evaluation_payload = {}

        if user_answer.answer_data:
            evaluation_payload["answer_data"] = user_answer.answer_data

        subsection = question.subsection.name
        subsection_obj = question.subsection

        if subsection_obj.ai_input_type == "audio":
            if not user_answer.transcribed_audio_data:
                raise Exception("Audio transcription not completed yet")
            evaluation_payload["transcribed_audio_data"] = user_answer.transcribed_audio_data

        # -------------------------
        # RULE-BASED SHORT CIRCUIT
        # -------------------------
        if subsection_obj.evaluation_type == "rule":
            evaluation_result = run_rule_evaluation(
                user_answer=user_answer,
                question=question,
                subsection=subsection_obj,
            )
        else:
            # -------------------------
            # AI-BASED EVALUATION
            # -------------------------

            try:
                evaluation_result = run_evaluation(
                    subsection,
                    question.text,
                    evaluation_payload
                )
            except Exception as e:
                return {"error": "Error during evaluation", "details": str(e)}

        with transaction.atomic():

            # 1️⃣ Save raw evaluation output
            user_answer.evaluation_result = evaluation_result
            user_answer.save(update_fields=["evaluation_result"])

            # 2️⃣ Apply trait → skill routing (UserResponse)
            user_answer.apply_skill_scores()

            # 3️⃣ Aggregate to session totals (UserMockTestSession)
            user_answer.user_session.aggregate_scores()

        return {
            "status": "success",
            "user_answer_id": user_answer_id,
            "question_id": question_id,
            "subsection": subsection,
            "evaluation_result": evaluation_result,
        }

    except Exception as e:
        return {"error": "Unexpected error occurred", "details": str(e)}
    


##### single answer gimmiks


@shared_task(bind=True)
def transcribe_single_task(self,user_response_id,):
    user_response = SingleResponse.objects.get(id=user_response_id)

    input_path = user_response.answer_audio.path
    output_path = f"/tmp/{uuid.uuid4()}.wav"

    # Convert audio to wav
    subprocess.run([
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        output_path
    ], check=True)

    transcript = transcribe_and_analyse(output_path)

    user_response.transcribed_audio_data = transcript
    user_response.save()

    os.remove(output_path)

    return user_response_id

@shared_task
def evaluate_single_response(user_answer_id, question_id):
    print("Evaluation begins...")

    try:
        try:
            user_answer = SingleResponse.objects.get(id=user_answer_id)
        except SingleResponse.DoesNotExist:
            return {"error": f"UserResponse {user_answer_id} does not exist"}

        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return {"error": f"Question {question_id} does not exist"}

        if not question.subsection:
            return {"error": f"Question {question_id} has no subsection assigned"}
        
        evaluation_payload = {}

        if user_answer.answer_data:
            evaluation_payload["answer_data"] = user_answer.answer_data

        subsection = question.subsection.name
        subsection_obj = question.subsection

        if subsection_obj.ai_input_type == "audio":
            if not user_answer.transcribed_audio_data:
                raise Exception("Audio transcription not completed yet")
            evaluation_payload["transcribed_audio_data"] = user_answer.transcribed_audio_data

        # -------------------------
        # RULE-BASED SHORT CIRCUIT
        # -------------------------
        if subsection_obj.evaluation_type == "rule":
            evaluation_result = run_rule_evaluation(
                user_answer=user_answer,
                question=question,
                subsection=subsection_obj,
            )
        else:
            # -------------------------
            # AI-BASED EVALUATION
            # -------------------------

            try:
                evaluation_result = run_evaluation(
                    subsection,
                    question.text,
                    evaluation_payload
                )
            except Exception as e:
                return {"error": "Error during evaluation", "details": str(e)}

        with transaction.atomic():

            # 1️⃣ Save raw evaluation output
            user_answer.evaluation_result = evaluation_result
            user_answer.save(update_fields=["evaluation_result"])

            # 2️⃣ Apply trait → skill routing (UserResponse)
            user_answer.apply_skill_scores()

            # 3️⃣ Aggregate to session totals (UserMockTestSession)
            # user_answer.user_session.aggregate_scores()

        return {
            "status": "success",
            "user_answer_id": user_answer_id,
            "question_id": question_id,
            "subsection": subsection,
            "evaluation_result": evaluation_result,
        }

    except Exception as e:
        return {"error": "Unexpected error occurred", "details": str(e)}
    