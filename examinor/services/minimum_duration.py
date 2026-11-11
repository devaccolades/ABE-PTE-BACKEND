"""Company policy: a spoken answer shorter than the minimum recording length scores zero."""

import math

from django.conf import settings

from examinor.services.repetitive_answer import apply_answer_integrity_override


# Seconds of recording below which the whole answer receives zero. This is a
# company rule; Pearson's score guide sets no minimum length for these tasks.
MINIMUM_RECORDING_SECONDS = {
    "summarise_group_discussion": 50,
}


def inspect_minimum_duration(task_type, evaluation_payload):
    enabled = getattr(settings, "MINIMUM_DURATION_POLICY_ENABLED", True)
    minimum = MINIMUM_RECORDING_SECONDS.get(task_type)
    duration = _recording_seconds(evaluation_payload)
    # Without a measured length there is no evidence either way, so no zero.
    applicable = enabled and minimum is not None and duration is not None
    too_short = applicable and duration < minimum
    if too_short:
        reason = (
            f"Company policy requires a recording of at least {minimum} seconds for this "
            f"task; this recording is {math.floor(duration)} seconds. The whole answer "
            "receives zero."
        )
    elif applicable:
        reason = "The recording meets the company minimum length."
    else:
        reason = "Minimum recording length policy is not applicable."
    return {
        "detector_version": "company-minimum-duration-v1",
        "policy_source": "company",
        "enabled": enabled,
        "applicable": applicable,
        "is_too_short": too_short,
        "duration_seconds": duration,
        "minimum_seconds": minimum,
        "reason": reason,
    }


def apply_minimum_duration_override(result, detection):
    if not detection["applicable"]:
        return result
    return apply_answer_integrity_override(
        result, detection, check_name="minimum_duration", trigger_field="is_too_short",
        override_code="company_minimum_duration",
    )


def apply_minimum_duration_policy(result, task_type, evaluation_payload):
    detection = inspect_minimum_duration(task_type, evaluation_payload)
    result = apply_minimum_duration_override(result, detection)
    if detection["is_too_short"]:
        feedback = (result.get("evaluation") or {}).get("feedback")
        if isinstance(feedback, dict):
            feedback["summary"] = detection["reason"]
    return result


def _recording_seconds(evaluation_payload):
    transcript = (evaluation_payload or {}).get("transcribed_audio_data")
    metadata = transcript.get("audio_metadata") if isinstance(transcript, dict) else None
    duration = metadata.get("duration_seconds") if isinstance(metadata, dict) else None
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        return None
    if not math.isfinite(duration) or duration <= 0:
        return None
    return float(duration)
