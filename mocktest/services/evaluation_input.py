from dataclasses import dataclass

from examinor.scoring.task_contracts import (
    get_task_contract,
    has_usable_transcript,
)


MISSING_RESPONSE_AUDIO_CODE = "response_audio_missing"
MISSING_RESPONSE_AUDIO_MESSAGE = (
    "Original response audio is missing; upload a replacement recording before "
    "retrying transcription and evaluation."
)


@dataclass(frozen=True, slots=True)
class EvaluationInputIssue:
    code: str
    message: str
    retryable: bool

    def as_result(self, *, stage="submission"):
        return {
            "ok": False,
            "stage": stage,
            "code": self.code,
            "error": self.message,
            "retryable": self.retryable,
        }


def question_requires_audio(question):
    subsection = getattr(question, "subsection", None)
    if subsection is None:
        return False
    return get_task_contract(subsection.name).requires_response_audio


def response_input_issue(response):
    if not question_requires_audio(response.question):
        return None

    audio = getattr(response, "answer_audio", None)
    has_audio = bool(audio and audio.name)
    has_transcript = has_usable_transcript(
        getattr(response, "transcribed_audio_data", None)
    )
    if has_audio or has_transcript:
        return None

    return EvaluationInputIssue(
        code=MISSING_RESPONSE_AUDIO_CODE,
        message=MISSING_RESPONSE_AUDIO_MESSAGE,
        retryable=False,
    )
