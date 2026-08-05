import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class TaskContractError(ValueError):
    """Raised when a subsection has no reviewed evaluation contract."""


class AnswerKind(str, Enum):
    AUDIO_UPLOAD = "audio_upload"
    BLANK_MAPPING = "blank_mapping"
    ORDERED_MAPPING = "ordered_mapping"
    SINGLE_OPTION_ID = "single_option_id"
    MULTIPLE_OPTION_IDS = "multiple_option_ids"
    DELIMITED_TEXT = "delimited_text"
    FREE_TEXT = "free_text"


class EvaluationEngine(str, Enum):
    AI = "ai"
    RULE = "rule"


class PayloadStatus(str, Enum):
    CANONICAL = "canonical"
    LEGACY_COMPATIBLE = "legacy_compatible"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class TaskContract:
    subsection: str
    answer_kind: AnswerKind
    evaluation_engine: EvaluationEngine
    gate_traits: tuple[str, ...] = ()

    @property
    def requires_response_audio(self):
        return self.answer_kind == AnswerKind.AUDIO_UPLOAD


@dataclass(frozen=True, slots=True)
class PayloadIssue:
    code: str
    message: str

    def as_dict(self):
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class AnswerPayloadInspection:
    status: PayloadStatus
    normalized: object
    issues: tuple[PayloadIssue, ...] = ()

    @property
    def usable(self):
        return self.status != PayloadStatus.INVALID

    def as_dict(self):
        return {
            "status": self.status.value,
            "usable": self.usable,
            "normalized": self.normalized,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def _task(
    subsection,
    answer_kind,
    evaluation_engine,
    *,
    gate_traits=(),
):
    return TaskContract(
        subsection=subsection,
        answer_kind=answer_kind,
        evaluation_engine=evaluation_engine,
        gate_traits=tuple(gate_traits),
    )


# This registry describes effective evaluation behavior. In particular,
# write_from_dictation is deterministic even if an older database row says AI.
TASK_CONTRACTS = MappingProxyType({
    # Speaking
    "read_aloud": _task(
        "read_aloud",
        AnswerKind.AUDIO_UPLOAD,
        EvaluationEngine.AI,
        gate_traits=("content",),
    ),
    "repeat_sentence": _task(
        "repeat_sentence",
        AnswerKind.AUDIO_UPLOAD,
        EvaluationEngine.AI,
        gate_traits=("content",),
    ),
    "describe_image": _task(
        "describe_image",
        AnswerKind.AUDIO_UPLOAD,
        EvaluationEngine.AI,
        gate_traits=("content",),
    ),
    "retell_lecture": _task(
        "retell_lecture",
        AnswerKind.AUDIO_UPLOAD,
        EvaluationEngine.AI,
        gate_traits=("content",),
    ),
    "answer_short_question": _task(
        "answer_short_question",
        AnswerKind.AUDIO_UPLOAD,
        EvaluationEngine.AI,
    ),
    "summarise_group_discussion": _task(
        "summarise_group_discussion",
        AnswerKind.AUDIO_UPLOAD,
        EvaluationEngine.AI,
        gate_traits=("content",),
    ),
    "respond_to_a_situation": _task(
        "respond_to_a_situation",
        AnswerKind.AUDIO_UPLOAD,
        EvaluationEngine.AI,
        gate_traits=("content",),
    ),
    # Writing
    "summarize_written_text": _task(
        "summarize_written_text",
        AnswerKind.FREE_TEXT,
        EvaluationEngine.AI,
        gate_traits=("content", "form"),
    ),
    "write_essay": _task(
        "write_essay",
        AnswerKind.FREE_TEXT,
        EvaluationEngine.AI,
        gate_traits=("content", "form"),
    ),
    # Reading
    "fib_dropdown": _task(
        "fib_dropdown",
        AnswerKind.BLANK_MAPPING,
        EvaluationEngine.RULE,
    ),
    "mc_multiple": _task(
        "mc_multiple",
        AnswerKind.MULTIPLE_OPTION_IDS,
        EvaluationEngine.RULE,
    ),
    "reorder_paragraphs": _task(
        "reorder_paragraphs",
        AnswerKind.ORDERED_MAPPING,
        EvaluationEngine.RULE,
    ),
    "fib_drag_drop": _task(
        "fib_drag_drop",
        AnswerKind.BLANK_MAPPING,
        EvaluationEngine.RULE,
    ),
    "mc_single": _task(
        "mc_single",
        AnswerKind.SINGLE_OPTION_ID,
        EvaluationEngine.RULE,
    ),
    # Listening
    "summarize_spoken_text": _task(
        "summarize_spoken_text",
        AnswerKind.FREE_TEXT,
        EvaluationEngine.AI,
        gate_traits=("content", "form"),
    ),
    "l_mc_multiple": _task(
        "l_mc_multiple",
        AnswerKind.MULTIPLE_OPTION_IDS,
        EvaluationEngine.RULE,
    ),
    "l_fill_in_blanks": _task(
        "l_fill_in_blanks",
        AnswerKind.DELIMITED_TEXT,
        EvaluationEngine.RULE,
    ),
    "highlight_correct_summary": _task(
        "highlight_correct_summary",
        AnswerKind.SINGLE_OPTION_ID,
        EvaluationEngine.RULE,
    ),
    "l_mc_single": _task(
        "l_mc_single",
        AnswerKind.SINGLE_OPTION_ID,
        EvaluationEngine.RULE,
    ),
    "select_missing_word": _task(
        "select_missing_word",
        AnswerKind.SINGLE_OPTION_ID,
        EvaluationEngine.RULE,
    ),
    "highlight_incorrect_words": _task(
        "highlight_incorrect_words",
        AnswerKind.FREE_TEXT,
        EvaluationEngine.AI,
    ),
    "write_from_dictation": _task(
        "write_from_dictation",
        AnswerKind.FREE_TEXT,
        EvaluationEngine.RULE,
    ),
})


LEGACY_WRAPPER_KEYS = (
    "answer",
    "value",
    "selected",
    "selected_id",
    "selected_option",
    "selected_option_id",
    "selected_options",
    "selected_ids",
    "option_id",
    "option_ids",
    "choices",
    "text",
)

DELIMITED_TEXT_RE = re.compile(r"[,|\n;]+")


def get_task_contract(subsection_name):
    try:
        return TASK_CONTRACTS[subsection_name]
    except (KeyError, TypeError) as exc:
        raise TaskContractError(
            f"No evaluation task contract for subsection '{subsection_name}'."
        ) from exc


def has_usable_transcript(transcribed_audio_data):
    if isinstance(transcribed_audio_data, str):
        return bool(transcribed_audio_data.strip())
    if not isinstance(transcribed_audio_data, Mapping):
        return False

    transcription = transcribed_audio_data.get("transcription")
    if isinstance(transcription, str):
        return bool(transcription.strip())
    if isinstance(transcription, Mapping):
        text = transcription.get("text")
        if isinstance(text, str) and text.strip():
            return True

    legacy_text = transcribed_audio_data.get("text")
    return isinstance(legacy_text, str) and bool(legacy_text.strip())


def inspect_answer_payload(
    subsection_name,
    answer_data,
    *,
    has_audio=False,
    has_transcript=False,
):
    """Classify a stored answer without changing or persisting it."""
    contract = get_task_contract(subsection_name)

    if contract.answer_kind == AnswerKind.AUDIO_UPLOAD:
        return _inspect_audio(has_audio=has_audio, has_transcript=has_transcript)
    if contract.answer_kind in {
        AnswerKind.BLANK_MAPPING,
        AnswerKind.ORDERED_MAPPING,
    }:
        return _inspect_mapping(answer_data)
    if contract.answer_kind == AnswerKind.SINGLE_OPTION_ID:
        return _inspect_single_option(answer_data)
    if contract.answer_kind == AnswerKind.MULTIPLE_OPTION_IDS:
        return _inspect_multiple_options(answer_data)
    if contract.answer_kind == AnswerKind.DELIMITED_TEXT:
        return _inspect_delimited_text(answer_data)
    if contract.answer_kind == AnswerKind.FREE_TEXT:
        return _inspect_free_text(answer_data)

    raise TaskContractError(
        f"Unsupported answer kind '{contract.answer_kind}' for {subsection_name}."
    )


def _issue(code, message):
    return PayloadIssue(code=code, message=message)


def _canonical(normalized):
    return AnswerPayloadInspection(
        status=PayloadStatus.CANONICAL,
        normalized=normalized,
    )


def _compatible(normalized, issues):
    return AnswerPayloadInspection(
        status=PayloadStatus.LEGACY_COMPATIBLE,
        normalized=normalized,
        issues=tuple(issues),
    )


def _invalid(*issues):
    return AnswerPayloadInspection(
        status=PayloadStatus.INVALID,
        normalized=None,
        issues=tuple(issues),
    )


def _inspect_audio(*, has_audio, has_transcript):
    if has_audio:
        return _canonical({"response_source": "audio"})
    if has_transcript:
        return _compatible(
            {"response_source": "stored_transcript"},
            (
                _issue(
                    "transcript_without_audio",
                    "A transcript exists, but the original response audio is missing.",
                ),
            ),
        )
    return _invalid(
        _issue(
            "response_audio_missing",
            "Neither response audio nor a recoverable transcript is stored.",
        )
    )


def _unwrap_legacy_wrapper(answer_data):
    if not isinstance(answer_data, Mapping):
        return answer_data, (), None

    wrapper_keys = [key for key in LEGACY_WRAPPER_KEYS if key in answer_data]
    if len(wrapper_keys) > 1:
        return None, (), _issue(
            "ambiguous_answer_wrapper",
            "The answer object contains more than one recognized wrapper key.",
        )
    if not wrapper_keys:
        return answer_data, (), None

    key = wrapper_keys[0]
    return (
        answer_data[key],
        (
            _issue(
                "legacy_answer_wrapper",
                f"The answer uses the legacy '{key}' wrapper.",
            ),
        ),
        None,
    )


def _decode_json_container(value, expected_prefix):
    if not isinstance(value, str) or not value.lstrip().startswith(expected_prefix):
        return value, (), None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return value, (), None
    return (
        decoded,
        (
            _issue(
                "json_encoded_answer",
                "The structured answer was stored as a JSON string.",
            ),
        ),
        None,
    )


def _positive_integer(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            number = int(value)
            return number if number > 0 else None
    return None


def _inspect_mapping(answer_data):
    value, issues, wrapper_error = _unwrap_legacy_wrapper(answer_data)
    if wrapper_error:
        return _invalid(wrapper_error)

    value, json_issues, _ = _decode_json_container(value, "{")
    issues += json_issues
    if not isinstance(value, Mapping):
        return _invalid(
            _issue(
                "mapping_required",
                "The answer must map blank or position numbers to option IDs.",
            )
        )
    if not value:
        return _invalid(
            _issue("answer_required", "At least one mapped answer is required.")
        )

    normalized = {}
    selected_ids = set()
    for raw_key, raw_value in value.items():
        key = _positive_integer(raw_key)
        option_id = _positive_integer(raw_value)
        if key is None or option_id is None:
            return _invalid(
                _issue(
                    "invalid_mapping_identifier",
                    "Mapping keys and option IDs must be positive integers.",
                )
            )
        if key in normalized:
            return _invalid(
                _issue(
                    "duplicate_mapping_position",
                    "The answer maps the same normalized position more than once.",
                )
            )
        if option_id in selected_ids:
            return _invalid(
                _issue(
                    "duplicate_option_selection",
                    "The same option ID is selected more than once.",
                )
            )
        normalized[key] = option_id
        selected_ids.add(option_id)

    normalized = {str(key): normalized[key] for key in sorted(normalized)}
    if issues:
        return _compatible(normalized, issues)
    return _canonical(normalized)


def _inspect_single_option(answer_data):
    value, issues, wrapper_error = _unwrap_legacy_wrapper(answer_data)
    if wrapper_error:
        return _invalid(wrapper_error)

    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            return _invalid(
                _issue(
                    "single_option_required",
                    "A single-choice answer must contain exactly one option ID.",
                )
            )
        value = value[0]
        issues += (
            _issue(
                "single_option_list",
                "A single-choice answer was stored as a one-item list.",
            ),
        )

    option_id = _positive_integer(value)
    if option_id is None:
        return _invalid(
            _issue(
                "invalid_option_id",
                "The selected option ID must be a positive integer.",
            )
        )
    if issues:
        return _compatible(option_id, issues)
    return _canonical(option_id)


def _inspect_multiple_options(answer_data):
    value, issues, wrapper_error = _unwrap_legacy_wrapper(answer_data)
    if wrapper_error:
        return _invalid(wrapper_error)

    value, json_issues, _ = _decode_json_container(value, "[")
    issues += json_issues

    if isinstance(value, str) and "," in value:
        parts = [part.strip() for part in value.split(",")]
        if not parts or any(not part for part in parts):
            return _invalid(
                _issue(
                    "invalid_delimited_option_ids",
                    "Comma-delimited option IDs cannot contain empty items.",
                )
            )
        value = parts
        issues += (
            _issue(
                "delimited_multiple_choice_answer",
                "Multiple-choice option IDs were stored as a comma-delimited string.",
            ),
        )

    if not isinstance(value, (list, tuple)):
        if isinstance(value, str) and not value.strip():
            return _invalid(
                _issue("answer_required", "At least one selected option is required.")
            )
        option_id = _positive_integer(value)
        if option_id is None:
            return _invalid(
                _issue(
                    "option_id_list_required",
                    "A multiple-choice answer must be a list of option IDs.",
                )
            )
        value = [option_id]
        issues += (
            _issue(
                "scalar_multiple_choice_answer",
                "A multiple-choice answer was stored as a scalar option ID.",
            ),
        )

    if not value:
        return _invalid(
            _issue("answer_required", "At least one selected option is required.")
        )

    normalized = []
    seen = set()
    for raw_value in value:
        option_id = _positive_integer(raw_value)
        if option_id is None:
            return _invalid(
                _issue(
                    "invalid_option_id",
                    "Every selected option ID must be a positive integer.",
                )
            )
        if option_id in seen:
            return _invalid(
                _issue(
                    "duplicate_option_selection",
                    "The same option ID is selected more than once.",
                )
            )
        seen.add(option_id)
        normalized.append(option_id)

    if issues:
        return _compatible(normalized, issues)
    return _canonical(normalized)


def _inspect_delimited_text(answer_data):
    value, issues, wrapper_error = _unwrap_legacy_wrapper(answer_data)
    if wrapper_error:
        return _invalid(wrapper_error)

    if isinstance(value, Mapping):
        ordered = []
        for raw_key, raw_value in value.items():
            key = _positive_integer(raw_key)
            if key is None or not isinstance(raw_value, str) or not raw_value.strip():
                return _invalid(
                    _issue(
                        "invalid_delimited_text_mapping",
                        "Mapped blank answers require positive keys and non-empty text.",
                    )
                )
            ordered.append((key, raw_value.strip()))
        if not ordered:
            return _invalid(
                _issue("answer_required", "At least one text answer is required.")
            )
        value = [text for _, text in sorted(ordered)]
        issues += (
            _issue(
                "mapped_delimited_text",
                "Delimited text answers were stored as a position mapping.",
            ),
        )

    if isinstance(value, (list, tuple)):
        normalized = [
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        ]
        if len(normalized) != len(value) or not normalized:
            return _invalid(
                _issue(
                    "invalid_delimited_text_items",
                    "Every blank answer must contain non-empty text.",
                )
            )
        issues += (
            _issue(
                "delimited_text_list",
                "Delimited text answers were stored as a list.",
            ),
        )
        return _compatible(normalized, issues)

    if not isinstance(value, str):
        return _invalid(
            _issue(
                "text_answer_required",
                "The answer must be a non-empty delimited text string.",
            )
        )
    normalized = [item.strip() for item in DELIMITED_TEXT_RE.split(value) if item.strip()]
    if not normalized:
        return _invalid(
            _issue("answer_required", "At least one text answer is required.")
        )
    if issues:
        return _compatible(normalized, issues)
    return _canonical(normalized)


def _inspect_free_text(answer_data):
    value, issues, wrapper_error = _unwrap_legacy_wrapper(answer_data)
    if wrapper_error:
        return _invalid(wrapper_error)
    if not isinstance(value, str) or not value.strip():
        return _invalid(
            _issue("answer_required", "A non-empty text answer is required.")
        )

    normalized = value.strip()
    if issues:
        return _compatible(normalized, issues)
    return _canonical(normalized)
