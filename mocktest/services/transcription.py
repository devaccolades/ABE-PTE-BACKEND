
import os
# import librosa
import soundfile as sf
from openai import OpenAI
from django.conf import settings

from examinor.services.openai_errors import format_openai_error
from .audio_analysis import analyse_speech




# -----------------------------------------
#  STEP 1: Transcribe audio using Whisper
# -----------------------------------------
def transcribe_audio(audio_file_path: str):
    """
    Returns:
        text (str)
        word_timestamps: [{word,start,end}, ...]
    """
    if not settings.OPENAI_WHISPER_API_KEY:
        raise RuntimeError(
            "OPENAI_WHISPER_API_KEY is missing. Set it in the Django and Celery worker environment."
        )

    whisper_client = OpenAI(
        api_key=settings.OPENAI_WHISPER_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    try:
        with open(audio_file_path, "rb") as audio_file:
            response = whisper_client.audio.transcriptions.create(
                model=settings.OPENAI_TRANSCRIPTION_MODEL,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
    except Exception as e:
        raise RuntimeError(f"{format_openai_error(e)}: {e}") from e

    transcription_text = response.text
    word_timestamps = response.words  # list of word-level timestamps

    return transcription_text, word_timestamps


# -----------------------------------------
#  STEP 2: FULL PIPELINE = TRANSCRIBE + ANALYSE
# -----------------------------------------
def transcribe_and_analyse(audio_file_path: str):
    """
    Complete workflow:
    - Transcribe audio via Whisper
    - Compute audio duration
    - Run your pronunciation & fluency analysis
    - Return FINAL JSON REPORT
    """

    # 1. Duration of audio-librosa package
    # audio_data, sr = librosa.load(audio_file_path)
    # duration = librosa.get_duration(y=audio_data, sr=sr)

    audio_data, samplerate = sf.read(audio_file_path)
     # If stereo → convert to mono
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)

    duration = len(audio_data) / samplerate


    # 2. Transcription
    text, timestamps = transcribe_audio(audio_file_path)

    # 3. Analysis (your existing function)
    report = analyse_speech(
        transcription_text=text,
        word_timestamps=[{
            "word": w.word,
            "start": w.start,
            "end": w.end
        } for w in timestamps],
        audio_duration=duration
    )

    return report
