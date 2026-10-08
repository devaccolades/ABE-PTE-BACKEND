import re
from copy import deepcopy
from difflib import SequenceMatcher
from html import unescape


WORD_RE = re.compile(r"[^\W_]+(?:['-][^\W_]+)?", re.UNICODE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
REFERENCE_CONTENT_TASKS = {"read_aloud", "repeat_sentence"}


def apply_speech_score_guardrails(
    evaluation,
    *,
    task_type,
    question_text,
    evaluation_payload,
):
    """Cap speech scores using deterministic evidence stored with the transcript."""
    result = deepcopy(evaluation)
    scores = result.get("scores")
    if not isinstance(scores, dict):
        return result

    transcript_data = evaluation_payload.get("transcribed_audio_data")
    if not isinstance(transcript_data, dict):
        return result

    adjustments = []
    if task_type in REFERENCE_CONTENT_TASKS and "content" in scores:
        answer = _transcript_text(transcript_data)
        maximum = _score_maximum(scores["content"])
        content_cap, similarity = _content_cap(
            task_type,
            question_text,
            answer,
            maximum,
        )
        _cap_score(
            scores,
            "content",
            content_cap,
            adjustments,
            reason="reference_word_alignment",
            evidence={"word_alignment_ratio": similarity},
        )

    if transcript_data.get("analysis_version") == "speech-evidence-v2":
        fluency_band = _nested_number(
            transcript_data,
            "fluency_analysis",
            "overall_score_0_to_5",
        )
        if fluency_band is not None:
            _cap_score(
                scores,
                "oral_fluency",
                fluency_band,
                adjustments,
                reason="measured_fluency_band",
            )

        pronunciation_band = _nested_number(
            transcript_data,
            "pronunciation_analysis",
            "overall_score_0_to_5",
        )
        if pronunciation_band is not None:
            _cap_score(
                scores,
                "pronunciation",
                pronunciation_band,
                adjustments,
                reason="acoustic_recognition_confidence",
            )

    if adjustments:
        result["score_guardrails"] = adjustments
        result["weighted_score"] = sum(
            float(payload.get("score") or 0)
            for payload in scores.values()
            if isinstance(payload, dict)
        )
    return result


def _content_cap(task_type, reference, answer, maximum):
    reference_tokens = _tokens(reference)
    answer_tokens = _tokens(answer)
    if not reference_tokens or not answer_tokens:
        return 0.0, 0.0
    similarity = SequenceMatcher(
        None,
        reference_tokens,
        answer_tokens,
        autojunk=False,
    ).ratio()
    if task_type == "repeat_sentence":
        if similarity >= 0.80:
            cap = maximum
        elif similarity >= 0.55:
            cap = min(maximum, 2.0)
        elif similarity >= 0.25:
            cap = min(maximum, 1.0)
        else:
            cap = 0.0
    else:
        cap = round(similarity * maximum)
    return float(cap), round(similarity, 4)


def _cap_score(scores, key, cap, adjustments, *, reason, evidence=None):
    payload = scores.get(key)
    if not isinstance(payload, dict):
        return
    current = float(payload.get("score") or 0)
    maximum = _score_maximum(payload)
    normalized_cap = min(max(float(cap), 0.0), maximum)
    if current <= normalized_cap:
        return
    payload["score"] = normalized_cap
    adjustment = {
        "criterion": key,
        "original_score": current,
        "adjusted_score": normalized_cap,
        "reason": reason,
    }
    if evidence:
        adjustment["evidence"] = evidence
    adjustments.append(adjustment)


def _transcript_text(transcript_data):
    transcription = transcript_data.get("transcription")
    if isinstance(transcription, dict):
        return str(transcription.get("text") or "")
    return str(transcription or "")


def _tokens(value):
    text = unescape(HTML_TAG_RE.sub(" ", str(value or "")))
    return [token.casefold() for token in WORD_RE.findall(text)]


def _score_maximum(payload):
    return float(payload.get("max", payload.get("maximum")) or 0)


def _nested_number(value, *keys):
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    try:
        return float(current)
    except (TypeError, ValueError):
        return None
