"""Conservative ASR reliability checks, separate from candidate scoring."""

import math

from django.conf import settings


class TranscriptionReliabilityError(RuntimeError):
    def __init__(self, report):
        super().__init__(
            "The recording could not be transcribed reliably. "
            "Review the original audio or upload a clearer recording before retrying."
        )
        self.report = report


def inspect_transcription_quality(text, segments, *, silent_audio=False):
    config = getattr(settings, "TRANSCRIPTION_RELIABILITY_CONFIG", {})
    suspicious = []
    evidence = []
    for index, segment in enumerate(segments or []):
        get = segment.get if isinstance(segment, dict) else lambda key: getattr(segment, key, None)
        row = {key: _finite_number(get(key)) for key in (
            "start", "end", "avg_logprob", "no_speech_prob", "compression_ratio",
        )}
        row["text"] = str(get("text") or "")
        evidence.append(row)
        # Poor recognition alone can be real, poorly pronounced speech. Require
        # both strong no-speech evidence and failed recognition to hold grading.
        if (
            row["text"].strip()
            and row["avg_logprob"] is not None
            and row["no_speech_prob"] is not None
            and row["avg_logprob"] < config.get("minimum_avg_logprob", -1.0)
            and row["no_speech_prob"] >= config.get("no_speech_threshold", 0.8)
        ):
            suspicious.append(index)
    blocked = silent_audio or bool(suspicious)
    return {
        "version": "transcription-reliability-v1",
        "status": "review_required" if blocked else "pass",
        "requires_review": blocked,
        "reason": (
            "The audio contains no measurable signal." if silent_audio else
            "ASR returned words in segments with strong no-speech and low-confidence evidence."
            if suspicious else "No strong transcription-reliability warning detected."
        ),
        "suspicious_segment_indices": suspicious,
        "recognition_evidence_available": bool(evidence),
        "segments": evidence,
        "raw_transcript": str(text or ""),
    }


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
