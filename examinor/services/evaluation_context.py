import base64
import binascii
import hashlib
from io import BytesIO

from PIL import Image

from examinor.services.prompt_builder import evaluation_answer_text, normalize_answer_text


REFERENCE_REQUIRED_TASKS = frozenset({
    "retell_lecture",
    "summarise_group_discussion",
    "summarize_spoken_text",
})
TASK_LABELS = {
    "retell_lecture": "Retell Lecture",
    "summarise_group_discussion": "Summarise Group Discussion",
    "summarize_spoken_text": "Summarize Spoken Text",
}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
IMAGE_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


class EvaluationContextError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

    def as_result(self):
        return {"ok": False, "code": self.code, "error": str(self), "retryable": False}


def question_source_payload(question):
    """Load examiner-only source material from the stored question."""
    payload = {"reference_answer": question.correct_answer or ""}
    if question.subsection.name != "describe_image":
        return payload

    image = question.image
    if not image or not image.name:
        raise EvaluationContextError(
            "missing_question_image",
            "Describe Image requires the question image before evaluation can run.",
        )
    try:
        with image.storage.open(image.name, "rb") as source:
            image_bytes = source.read(MAX_IMAGE_BYTES + 1)
    except OSError as exc:
        raise EvaluationContextError(
            "question_image_unavailable",
            "The question image could not be read. Restore or upload the image before retrying.",
        ) from exc
    payload["question_image"] = _image_from_bytes(image_bytes)
    return payload


def validate_evaluation_context(task_type, payload):
    """Fail before provider/cache use if the answer or required source is missing."""
    answer = evaluation_answer_text(payload)
    if not answer.strip():
        raise EvaluationContextError(
            "missing_candidate_answer",
            "A non-empty candidate answer or transcript is required for AI evaluation.",
        )
    reference = normalize_answer_text(payload.get("reference_answer"))
    if task_type in REFERENCE_REQUIRED_TASKS and not reference.strip():
        raise EvaluationContextError(
            "missing_ai_reference",
            f"{TASK_LABELS[task_type]} requires a reference transcript, model answer, "
            "or reviewed key points in the question's Correct answer field.",
        )

    normalized = dict(payload)
    image = None
    if task_type == "describe_image":
        raw_image = payload.get("question_image")
        if not raw_image:
            raise EvaluationContextError(
                "missing_question_image",
                "Describe Image requires the question image before evaluation can run.",
            )
        image = _image_from_data_url(raw_image)
        normalized["question_image"] = image

    evidence = {
        "candidate_answer_sha256": _text_hash(answer),
        "reference_answer_sha256": _text_hash(reference) if reference.strip() else None,
        "question_image_sha256": image["sha256"] if image else None,
    }
    return normalized, evidence


def _image_from_data_url(value):
    data_url = value.get("data_url") if isinstance(value, dict) else value
    if not isinstance(data_url, str):
        raise EvaluationContextError(
            "invalid_question_image",
            "Provide the question image as a base64 image data URL.",
        )
    header, separator, encoded = data_url.partition(",")
    if not separator or header not in {
        f"data:{mime};base64" for mime in IMAGE_MIME_TYPES.values()
    }:
        raise EvaluationContextError(
            "invalid_question_image",
            "Provide a PNG, JPEG, WebP, or non-animated GIF base64 image data URL.",
        )
    if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise EvaluationContextError(
            "invalid_question_image",
            "The question image exceeds the 20 MiB evaluation limit.",
        )
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EvaluationContextError(
            "invalid_question_image", "The question image contains invalid base64 data.",
        ) from exc
    return _image_from_bytes(image_bytes)


def _image_from_bytes(image_bytes):
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise EvaluationContextError(
            "invalid_question_image",
            "The question image is empty or exceeds the 20 MiB evaluation limit.",
        )
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            mime_type = IMAGE_MIME_TYPES.get(image.format)
            if not mime_type or getattr(image, "is_animated", False):
                raise EvaluationContextError(
                    "invalid_question_image",
                    "Use a PNG, JPEG, WebP, or non-animated GIF question image.",
                )
            image.verify()
    except EvaluationContextError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise EvaluationContextError(
            "invalid_question_image",
            "The question image is unreadable. Upload a valid image before retrying.",
        ) from exc
    return {
        "data_url": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}",
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
    }


def _text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
