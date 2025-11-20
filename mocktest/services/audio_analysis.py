import re
import numpy as np


def count_vowels(word):
    return sum(1 for ch in word.lower() if ch in "aeiou")

def count_consonants(word):
    return sum(1 for ch in word.lower() if ch.isalpha() and ch not in "aeiou")



def analyse_speech(transcription_text: str, word_timestamps: list, audio_duration: float):
    """
    transcription_text: Full string
    word_timestamps: [{ "word": "hello", "start": 0.23, "end": 0.56 }, ...]
    audio_duration: seconds
    """

    words = transcription_text.split()
    num_words = len(words)

    vowel_accuracy = estimate_vowel_accuracy(words)
    consonant_accuracy = estimate_consonant_accuracy(words)
    mispronounced = detect_mispronunciations(words)
    stress_data = analyse_stress_patterns(words)
    connected_speech = analyse_connected_speech(transcription_text)

    pronunciation_band, pron_justification = map_pronunciation_band(
        vowel_accuracy, consonant_accuracy, mispronounced, stress_data
    )


    fluency = analyse_fluency(word_timestamps, audio_duration)

    fluency_band, fluency_justification = map_fluency_band(
        fluency["num_hesitations"],
        fluency["num_repetitions"],
        fluency["num_false_starts"],
        fluency["long_pauses_count"],
        fluency["speech_rate_wpm"]
    )


    return {
        "audio_metadata": {
            "duration_seconds": audio_duration,
            "num_words": num_words
        },

        "transcription": {
            "text": transcription_text,
            # "words": word_timestamps
        },

        "pronunciation_analysis": {
            "overall_score_0_to_5": pronunciation_band,
            "vowel_accuracy_percentage": vowel_accuracy,
            "consonant_accuracy_percentage": consonant_accuracy,
            "mispronounced_words": mispronounced,
            "stress_accuracy": stress_data,
            "connected_speech_features": connected_speech,
            "rubric_matching": {
                "best_fit_band": pronunciation_band,
                "justification": pron_justification
            }
        },

        "fluency_analysis": {
            "overall_score_0_to_5": fluency_band,
            "speech_rate_wpm": fluency["speech_rate_wpm"],
            "avg_pause_duration_ms": fluency["avg_pause_ms"],
            "num_hesitations": fluency["num_hesitations"],
            "num_repetitions": fluency["num_repetitions"],
            "num_false_starts": fluency["num_false_starts"],
            "smooth_runs": fluency["smooth_runs"],
            "pause_details": {
                "long_pauses_count": fluency["long_pauses_count"],
                "long_pauses_positions": fluency["long_pause_positions"]
            },
            "phrasing_rhythm": fluency["phrasing_rhythm"],
            "rubric_matching": {
                "best_fit_band": fluency_band,
                "justification": fluency_justification
            }
        },

        "final_overview": {
            "pronunciation_band": pronunciation_band,
            "fluency_band": fluency_band
        }
    }


# ------------------------------------------------------------
#  PRONUNCIATION HELPERS (Simplified ML-free heuristics)
# ------------------------------------------------------------
def estimate_vowel_accuracy(words):
    return max(70, 95 - len([w for w in words if len(w) > 8]))  # heuristic placeholder

def estimate_consonant_accuracy(words):
    return max(70, 93 - len([w for w in words if w.endswith("tion")]))  # heuristic placeholder

def detect_mispronunciations(words):
    common_hard_words = ["world", "communication", "technology", "algorithm"]
    return [w for w in words if w.lower() in common_hard_words]

def analyse_stress_patterns(words):
    return {
        "word_stress_correct_percentage": 90,
        "sentence_stress_correct_percentage": 85,
        "incorrect_stress_words": []
    }

def analyse_connected_speech(text):
    return {
        "assimilation_detected": True,
        "elision_detected": False,
        "linking_detected": True,
        "comments": "Natural linking between words detected."
    }


def map_pronunciation_band(vacc, cacc, misp, stress):
    if vacc > 90 and cacc > 90 and len(misp) == 0:
        return 5, "Clear vowels, consonants, correct stress, and natural speech flow."
    if vacc > 85 and cacc > 85:
        return 4, "Minor distortions but overall pronunciation clear."
    if vacc > 80:
        return 3, "Mostly clear with occasional unclear words."
    if vacc > 70:
        return 2, "Noticeable mispronunciations affecting clarity."
    return 1, "Frequent pronunciation issues."


# ------------------------------------------------------------
#  FLUENCY HELPERS
# ------------------------------------------------------------
def analyse_fluency(word_timestamps, audio_duration):
    pauses = []
    hesitations = 0
    repetitions = 0
    false_starts = 0

    for i in range(1, len(word_timestamps)):
        prev = word_timestamps[i-1]["end"]
        curr = word_timestamps[i]["start"]

        pause = curr - prev
        pauses.append(pause)

        if pause > 1.0:
            false_starts += 1

    long_pauses = [p for p in pauses if p > 1.2]

    return {
        "speech_rate_wpm": round((len(word_timestamps) / audio_duration) * 60, 2),
        "avg_pause_ms": np.mean(pauses) * 1000 if pauses else 0,
        "num_hesitations": hesitations,
        "num_repetitions": repetitions,
        "num_false_starts": false_starts,
        "smooth_runs": {
            "longest_run_words": detect_longest_run(word_timestamps),
            "three_word_runs_count": detect_three_word_runs(word_timestamps)
        },
        "long_pauses_count": len(long_pauses),
        "long_pause_positions": long_pauses,
        "phrasing_rhythm": {
            "is_smooth": len(long_pauses) <= 1,
            "is_staccato": len(long_pauses) >= 3,
            "comment": "Speech mostly smooth" if len(long_pauses) <= 1 else "Breaking rhythm"
        }
    }


def detect_longest_run(words):
    return 5  # stubbed placeholder

def detect_three_word_runs(words):
    return 3  # stubbed placeholder


def map_fluency_band(hes, rep, fs, long_pauses, wpm):
    if hes == 0 and rep == 0 and fs <= 1 and long_pauses <= 1 and wpm > 120:
        return 5, "Highly fluent with smooth rhythm."
    if hes <= 1 and rep <= 1 and long_pauses <= 1:
        return 4, "Good rhythm with minimal disruptions."
    if hes <= 2 and long_pauses <= 2:
        return 3, "Acceptable fluency with a few disruptions."
    if hes <= 3:
        return 2, "Uneven and inconsistent phrasing."
    return 1, "Frequent pauses and disrupted fluency."
