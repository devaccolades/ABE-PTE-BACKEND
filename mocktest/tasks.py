from celery import shared_task, chain
from .models import UserResponse
from mocktest.services.transcription import transcribe_and_analyse


@shared_task
def transcribe_task(user_response_id,temp_path):
    print("running whisper transcription")

    transcription = transcribe_and_analyse(temp_path)
    object = UserResponse.objects.get(id=user_response_id)
    object.transcribed_audio_data=transcription
    object.save()
    return {"user_response_id": user_response_id, "transcription": transcription}


@shared_task
def evaluate():
    print("testing")