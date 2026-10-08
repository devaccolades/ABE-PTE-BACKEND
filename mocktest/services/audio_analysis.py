import math
import re

WORD_RE = re.compile(r"[^\W_]+(?:['-][^\W_]+)?", re.UNICODE)
FILLERS = {"ah", "eh", "erm", "er", "hmm", "mm", "uh", "uhh", "um", "umm"}


def analyse_speech(
    transcription_text: str,
    word_timestamps: list,
    audio_duration: float,
    recognition_segments: list | None = None,
):
    """Build measurable speech evidence from ASR timestamps and confidence."""
    tokens = _tokens(transcription_text)
    timestamps = _normalized_timestamps(word_timestamps)
    fluency = analyse_fluency(tokens, timestamps, audio_duration)
    recognition = analyse_recognition_confidence(recognition_segments or [])
    fluency_band, fluency_justification = map_fluency_band(fluency)
    pronunciation_band, pronunciation_justification = map_pronunciation_band(recognition)

    return {
        "analysis_version": "speech-evidence-v2",
        "audio_metadata": {
            "duration_seconds": max(float(audio_duration or 0), 0.0),
            "num_words": len(tokens),
        },
        "transcription": {"text": transcription_text},
        "pronunciation_analysis": {
            "overall_score_0_to_5": pronunciation_band,
            "evidence_available": recognition["evidence_available"],
            "asr_confidence_proxy": recognition["confidence"],
            "average_log_probability": recognition["average_log_probability"],
            "average_no_speech_probability": recognition["average_no_speech_probability"],
            "rubric_matching": {
                "best_fit_band": pronunciation_band,
                "justification": pronunciation_justification,
            },
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
                "long_pauses_positions": fluency["long_pause_positions"],
            },
            "phrasing_rhythm": fluency["phrasing_rhythm"],
            "rubric_matching": {
                "best_fit_band": fluency_band,
                "justification": fluency_justification,
            },
        },
        "final_overview": {
            "pronunciation_band": pronunciation_band,
            "fluency_band": fluency_band,
        },
    }


def analyse_fluency(tokens, word_timestamps, audio_duration):
    pauses = []
    pause_positions = []
    for index in range(1, len(word_timestamps)):
        pause = max(
            0.0,
            word_timestamps[index]["start"] - word_timestamps[index - 1]["end"],
        )
        pauses.append(pause)
        if pause >= 1.2:
            pause_positions.append(round(word_timestamps[index - 1]["end"], 3))

    filler_count = sum(token in FILLERS for token in tokens)
    repeated_count = _immediate_repetition_count(tokens)
    restart_count = sum(pause >= 0.8 for pause in pauses)
    duration = max(float(audio_duration or 0), 0.0)
    speech_rate = round((len(tokens) / duration) * 60, 2) if duration else 0.0
    longest_run, three_word_runs = _smooth_runs(word_timestamps)
    disruption_count = filler_count + repeated_count + restart_count

    return {
        "word_count": len(tokens),
        "speech_rate_wpm": speech_rate,
        "avg_pause_ms": round((sum(pauses) / len(pauses)) * 1000, 2) if pauses else 0.0,
        "num_hesitations": filler_count,
        "num_repetitions": repeated_count,
        "num_false_starts": restart_count,
        "disruption_count": disruption_count,
        "smooth_runs": {
            "longest_run_words": longest_run,
            "three_word_runs_count": three_word_runs,
        },
        "long_pauses_count": len(pause_positions),
        "long_pause_positions": pause_positions,
        "phrasing_rhythm": {
            "is_smooth": disruption_count <= 1 and not pause_positions,
            "is_staccato": restart_count >= 3 or len(pause_positions) >= 2,
            "comment": (
                "Speech rhythm is continuous."
                if disruption_count <= 1 and not pause_positions
                else "Speech contains measurable disruptions."
            ),
        },
    }


def map_fluency_band(fluency):
    words = fluency["word_count"]
    rate = fluency["speech_rate_wpm"]
    disruptions = fluency["disruption_count"]
    long_pauses = fluency["long_pauses_count"]
    longest_run = fluency["smooth_runs"]["longest_run_words"]

    if words < 3 or rate < 45:
        return 1, "Too little continuous speech or an extremely slow delivery."
    if rate < 70 or rate > 210 or disruptions >= 5 or long_pauses >= 3:
        return 2, "Delivery is uneven with substantial timing or continuity problems."
    if rate < 90 or rate > 195 or disruptions >= 3 or long_pauses >= 2:
        return 3, "Delivery is understandable but has several measurable disruptions."
    if (
        disruptions <= 1
        and long_pauses <= 1
        and longest_run >= min(words, 5)
        and 105 <= rate <= 180
    ):
        return 5, "Delivery has a natural rate and sustained continuous phrasing."
    return 4, "Delivery is generally continuous with limited measurable disruption."


def analyse_recognition_confidence(segments):
    weighted_log_probability = 0.0
    weighted_no_speech = 0.0
    total_weight = 0.0
    for segment in segments:
        average_log_probability = _number(segment, "avg_logprob")
        if average_log_probability is None:
            continue
        start = _number(segment, "start") or 0.0
        end = _number(segment, "end") or start
        weight = max(end - start, 0.1)
        weighted_log_probability += average_log_probability * weight
        weighted_no_speech += (_number(segment, "no_speech_prob") or 0.0) * weight
        total_weight += weight

    if not total_weight:
        return {
            "evidence_available": False,
            "confidence": None,
            "average_log_probability": None,
            "average_no_speech_probability": None,
        }

    average_log_probability = weighted_log_probability / total_weight
    average_no_speech_probability = weighted_no_speech / total_weight
    confidence = math.exp(min(average_log_probability, 0.0)) * (
        1.0 - min(max(average_no_speech_probability, 0.0), 1.0)
    )
    return {
        "evidence_available": True,
        "confidence": round(confidence, 4),
        "average_log_probability": round(average_log_probability, 4),
        "average_no_speech_probability": round(average_no_speech_probability, 4),
    }


def map_pronunciation_band(recognition):
    confidence = recognition["confidence"]
    if confidence is None:
        return None, "Pronunciation evidence was unavailable; no synthetic band was created."
    if confidence >= 0.88:
        return 5, "Speech was recognized with very high acoustic confidence."
    if confidence >= 0.76:
        return 4, "Speech was recognized with high acoustic confidence."
    if confidence >= 0.62:
        return 3, "Speech was recognized with moderate acoustic confidence."
    if confidence >= 0.45:
        return 2, "Speech had low acoustic recognition confidence."
    return 1, "Speech had very low acoustic recognition confidence."


def _tokens(text):
    return [token.casefold() for token in WORD_RE.findall(str(text or ""))]


def _normalized_timestamps(items):
    normalized = []
    for item in items or []:
        try:
            start = float(item.get("start", 0))
            end = float(item.get("end", start))
        except (AttributeError, TypeError, ValueError):
            continue
        normalized.append({"start": start, "end": max(end, start)})
    return normalized


def _immediate_repetition_count(tokens):
    repeats = sum(tokens[index] == tokens[index - 1] for index in range(1, len(tokens)))
    for width in (2, 3):
        index = width
        while index + width <= len(tokens):
            if tokens[index - width:index] == tokens[index:index + width]:
                repeats += 1
                index += width
            else:
                index += 1
    return repeats


def _smooth_runs(timestamps):
    if not timestamps:
        return 0, 0
    runs = []
    current = 1
    for index in range(1, len(timestamps)):
        gap = timestamps[index]["start"] - timestamps[index - 1]["end"]
        if gap < 0.8:
            current += 1
        else:
            runs.append(current)
            current = 1
    runs.append(current)
    return max(runs), sum(run // 3 for run in runs)


def _number(value, key):
    raw = value.get(key) if isinstance(value, dict) else getattr(value, key, None)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
