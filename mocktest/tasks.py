from celery import shared_task, chain
from .models import *
from mocktest.services.transcription import transcribe_and_analyse
from examinor.services.orchestrator import run_evaluation


@shared_task
def transcribe_task(user_response_id,temp_path):
    print("running whisper transcription")

    transcription = transcribe_and_analyse(temp_path)
    object = UserResponse.objects.get(id=user_response_id)
    object.transcribed_audio_data=transcription
    object.save()
    return {"user_response_id": user_response_id, "transcription": transcription}


@shared_task
def evaluate_user_response(user_answer_id, question_id, answer_data):
    user_answer = UserResponse.objects.get(id=user_answer_id)
    question = Question.objects.get(id=question_id)
    subsection = question.subsection.name
    evaluate = run_evaluation(subsection,question.text,answer_data)
    print("evaluations begins")
    