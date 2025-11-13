import openai
from django.conf import settings
from pathlib import Path
import tempfile
import re
from jiwer import wer

openai.api_key = settings.OPENAI_WHISPER_API_KEY

def transcribe_analyse(audio_path,question_text):

    """
    Transcribe audio with Whisper and extract detailed timing/speech features.
    """

    results = {
        "question_text": question_text or "",
        "user_transcript": "",
        "timing_data": {},
        "wer": None,
        "extra_features": {}
    }

    try:
        with open(audio_path, "rb") as audio_file:
            transcript = openai.Audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json"  # gives timestamps & segments
            )
        results["user_transcript"] = transcript.text.strip()
        segments = transcript.get("segments", [])
    except Exception as e:
        print(f"Whisper transcription failed: {e}")
        return {"error": "Transcription failed"}

    try:
        y, sr = librosa.load(audio_file_path, sr=None)
        total_duration = librosa.get_duration(y=y, sr=sr)

        # Extract segment-level timing from Whisper
        if segments:
            speech_durations = [s["end"] - s["start"] for s in segments]
            speech_duration = sum(speech_durations)
            pauses = [
                segments[i]["start"] - segments[i - 1]["end"]
                for i in range(1, len(segments))
                if segments[i]["start"] > segments[i - 1]["end"]
            ]
            pause_count = len(pauses)
            avg_pause_length = np.mean(pauses) if pauses else 0
            longest_pause = np.max(pauses) if pauses else 0
        else:
            speech_duration = total_duration
            pause_count = 0
            avg_pause_length = 0
            longest_pause = 0

        # Words per second (approx)
        words = len(results["user_transcript"].split())
        speech_rate = round(words / speech_duration, 2) if speech_duration > 0 else 0

        results["timing_data"] = {
            "total_duration": round(total_duration, 2),
            "speech_duration": round(speech_duration, 2),
            "pause_count": pause_count,
            "avg_pause_length": round(avg_pause_length, 2),
            "speech_rate_wps": speech_rate
        }

        results["extra_features"] = {
            "longest_pause": round(longest_pause, 2),
            "num_repetitions": count_repetitions(results["user_transcript"])
        }

    except Exception as e:
        print(f"Audio analysis failed: {e}")

        # 3️⃣ --- Optional: Word Error Rate (if question_text provided) ---
    if question_text:
        try:
            results["wer"] = round(wer(question_text.lower(), results["user_transcript"].lower()), 3)
        except Exception as e:
            print(f"WER calculation failed: {e}")
            results["wer"] = None

    return results

def count_repetitions(text: str):
    """Count simple repeated consecutive words."""
    words = re.findall(r"\b\w+\b", text.lower())
    return sum(1 for i in range(1, len(words)) if words[i] == words[i - 1])

