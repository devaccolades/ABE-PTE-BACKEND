import re
import unicodedata
from collections.abc import Mapping
from difflib import SequenceMatcher

from examinor.services.repetitive_answer import apply_answer_integrity_override


DETECTOR_VERSION = "known-answer-template-v1"
OVERRIDE_CODE = "known_template_dominated"

TOKEN_RE = re.compile(r"[^\W_]+(?:['-][^\W_]+)?", re.UNICODE)
PLACEHOLDER_RE = re.compile(
    r"\[\[[^\]]+\]\]|\[[^\]]+\]|<[^>]+>|_{2,}|\.{3,}|\u2026+",
    re.UNICODE,
)

DEFAULT_CONFIG = {
    "enabled": True,
    "minimum_block_words": 4,
    "moderate_match_ratio": 0.30,
}


def detect_known_template_answer(text, templates, answer_type=None, *, config=None):
    """Find whether fixed template language replaces question-specific content."""
    settings = dict(DEFAULT_CONFIG)
    if isinstance(config, Mapping):
        settings.update(config)

    answer_tokens = _tokens(text)
    word_count = len(answer_tokens)
    if not settings["enabled"]:
        return _empty_result(answer_type, word_count, "disabled")
    if not answer_tokens:
        return _empty_result(answer_type, 0, "pass")

    candidates = []
    for template in templates:
        candidate = _compare_template(answer_tokens, template, settings)
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return _empty_result(answer_type, word_count, "pass")

    best = max(
        candidates,
        key=lambda item: (
            item["answer_match_ratio"],
            item["matched_word_count"],
            item["template_match_ratio"],
        ),
    )
    enough_evidence = (
        best["matched_word_count"] >= best["minimum_matched_words"]
        and best["matched_block_count"] >= best["minimum_match_blocks"]
    )
    dominated = (
        enough_evidence
        and best["answer_match_ratio"] >= best["minimum_match_ratio"]
        and best["original_word_count"] <= best["maximum_original_words"]
    )
    moderate = (
        not dominated
        and enough_evidence
        and best["answer_match_ratio"] >= settings["moderate_match_ratio"]
    )

    if dominated:
        status = "hard_zero"
        reason = (
            "Most of the answer matches a known response framework and too "
            "little question-specific content remains."
        )
    elif moderate:
        status = "moderate"
        reason = (
            "Known framework language was used, but enough original content "
            "remains to avoid an automatic zero."
        )
    else:
        status = "pass"
        reason = "Known framework usage remained within the permitted limits."

    return {
        "detector_version": DETECTOR_VERSION,
        "answer_type": str(answer_type or ""),
        "status": status,
        "is_template_dominated": dominated,
        "template_usage_detected": enough_evidence,
        "word_count": word_count,
        "matched_template": {
            "id": best["template_id"],
            "name": best["template_name"],
            "version": best["template_version"],
        },
        "answer_match_ratio": best["answer_match_ratio"],
        "template_match_ratio": best["template_match_ratio"],
        "matched_word_count": best["matched_word_count"],
        "original_word_count": best["original_word_count"],
        "matched_block_count": best["matched_block_count"],
        "matched_passages": best["matched_passages"],
        "thresholds": {
            "minimum_match_ratio": best["minimum_match_ratio"],
            "maximum_original_words": best["maximum_original_words"],
            "minimum_matched_words": best["minimum_matched_words"],
            "minimum_match_blocks": best["minimum_match_blocks"],
        },
        "reason": reason,
    }


def apply_known_template_score_override(evaluation_result, detection):
    return apply_answer_integrity_override(
        evaluation_result,
        detection,
        check_name="known_template",
        trigger_field="is_template_dominated",
        override_code=OVERRIDE_CODE,
    )


def _compare_template(answer_tokens, template, settings):
    template_text = _value(template, "template_text", "")
    segments = [
        _tokens(segment)
        for segment in PLACEHOLDER_RE.split(str(template_text or ""))
    ]
    segments = [segment for segment in segments if segment]
    if not segments:
        return None

    intervals = []
    fixed_template_words = sum(len(segment) for segment in segments)
    for segment in segments:
        matcher = SequenceMatcher(None, segment, answer_tokens, autojunk=False)
        for block in matcher.get_matching_blocks():
            if block.size < settings["minimum_block_words"]:
                continue
            intervals.append((block.b, block.b + block.size))

    merged = _merge_intervals(intervals)
    matched_word_count = sum(end - start for start, end in merged)
    if not matched_word_count:
        return None

    word_count = len(answer_tokens)
    return {
        "template_id": _value(template, "pk", _value(template, "id", None)),
        "template_name": str(_value(template, "name", "Known template")),
        "template_version": str(_value(template, "version", "")),
        "answer_match_ratio": round(matched_word_count / word_count, 4),
        "template_match_ratio": round(
            matched_word_count / max(fixed_template_words, 1),
            4,
        ),
        "matched_word_count": matched_word_count,
        "original_word_count": word_count - matched_word_count,
        "matched_block_count": len(merged),
        "matched_passages": [
            {
                "text": " ".join(answer_tokens[start:end]),
                "word_count": end - start,
                "start_word": start,
                "end_word": end,
            }
            for start, end in merged[:10]
        ],
        "minimum_match_ratio": float(
            _value(template, "minimum_match_ratio", 0.60)
        ),
        "maximum_original_words": int(
            _value(template, "maximum_original_words", 25)
        ),
        "minimum_matched_words": int(
            _value(template, "minimum_matched_words", 24)
        ),
        "minimum_match_blocks": int(
            _value(template, "minimum_match_blocks", 3)
        ),
    }


def _value(item, key, default):
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _tokens(value):
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = normalized.casefold().replace("\u2019", "'").replace("\u2018", "'")
    return TOKEN_RE.findall(normalized)


def _merge_intervals(intervals):
    merged = []
    for start, end in sorted(set(intervals)):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _empty_result(answer_type, word_count, status):
    reason = {
        "disabled": "Known-template detection is disabled.",
        "pass": "No known response framework dominated the answer.",
    }[status]
    return {
        "detector_version": DETECTOR_VERSION,
        "answer_type": str(answer_type or ""),
        "status": status,
        "is_template_dominated": False,
        "template_usage_detected": False,
        "word_count": word_count,
        "matched_template": None,
        "answer_match_ratio": 0.0,
        "template_match_ratio": 0.0,
        "matched_word_count": 0,
        "original_word_count": word_count,
        "matched_block_count": 0,
        "matched_passages": [],
        "thresholds": {},
        "reason": reason,
    }
