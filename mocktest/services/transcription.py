
import os
import librosa
from openai import OpenAI
from django.conf import settings

from .audio_analysis import analyse_speech


whisper_client = OpenAI(api_key=settings.OPENAI_WHISPER_API_KEY)   # Whisper only


# -----------------------------------------
#  STEP 1: Transcribe audio using Whisper
# -----------------------------------------
def transcribe_audio(audio_file_path: str):
    """
    Returns:
        text (str)
        word_timestamps: [{word,start,end}, ...]
    """

    with open(audio_file_path, "rb") as audio_file:
        response = whisper_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"]
        )

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

    # 1. Duration of audio
    audio_data, sr = librosa.load(audio_file_path)
    duration = librosa.get_duration(y=audio_data, sr=sr)

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
