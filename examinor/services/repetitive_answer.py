import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from difflib import SequenceMatcher


DETECTOR_VERSION = "repetitive-answer-v1"
OVERRIDE_CODE = "repetitive_template_answer"

TOKEN_RE = re.compile(r"[^\W_]+(?:['-][^\W_]+)?", re.UNICODE)
SENTENCE_BOUNDARY_RE = re.compile(r"[.!?;:\n]+")

DEFAULT_CONFIG = {
    "enabled": True,
    "minimum_words": 35,
    "minimum_phrase_words": 3,
    "maximum_phrase_words": 8,
    "minimum_repeat_count": 3,
    "starter_words": 4,
    "minimum_similar_sentences": 3,
    "sentence_similarity_threshold": 0.78,
    "moderate_ratio_threshold": 0.25,
    "moderate_score_threshold": 0.50,
    "hard_ratio_threshold": 0.38,
    "hard_score_threshold": 0.72,
    "dominant_exact_ratio_threshold": 0.50,
    "lexical_diversity_floor": 0.55,
    "maximum_sentences": 80,
}

PROFILE_OVERRIDES = {
    "brief_spoken": {
        "minimum_words": 25,
    },
    "spoken_summary": {
        "minimum_words": 30,
    },
    "written_summary": {
        "minimum_words": 25,
    },
    "essay": {
        "minimum_words": 80,
        "hard_ratio_threshold": 0.36,
    },
}

ANSWER_TYPE_PROFILES = {
    "describe_image": "brief_spoken",
    "retell_lecture": "spoken_summary",
    "summarise_group_discussion": "spoken_summary",
    "respond_to_a_situation": "brief_spoken",
    "summarize_written_text": "written_summary",
    "write_essay": "essay",
    "summarize_spoken_text": "written_summary",
}


def detect_repetitive_answer(
    text,
    answer_type=None,
    *,
    profile=None,
    config=None,
):
    """Return deterministic repetition evidence without scoring the answer."""
    settings = _resolved_config(answer_type, profile, config)
    normalized = _normalize_text(text)
    tokens, sentence_ranges = _tokenize_with_sentences(normalized)
    word_count = len(tokens)

    if not settings["enabled"]:
        return _result(
            answer_type=answer_type,
            word_count=word_count,
            minimum_words=settings["minimum_words"],
            status="disabled",
            reason="Repetitive-answer detection is disabled.",
            profile=settings["profile"],
        )

    if not tokens:
        return _result(
            answer_type=answer_type,
            word_count=0,
            minimum_words=settings["minimum_words"],
            status="pass",
            reason="No text was available for repetition analysis.",
            profile=settings["profile"],
        )

    exact = _exact_repetition(tokens, sentence_ranges, settings)
    openings = _repeated_openings(tokens, sentence_ranges, settings)
    structure = _similar_sentence_structure(tokens, sentence_ranges, settings)

    repeated_positions = (
        exact["positions"] | openings["positions"] | structure["positions"]
    )
    repetition_ratio = len(repeated_positions) / word_count
    exact_ratio = len(exact["positions"]) / word_count
    opening_ratio = len(openings["positions"]) / word_count
    structural_ratio = len(structure["positions"]) / word_count
    lexical_diversity = _moving_lexical_diversity(tokens)
    lexical_penalty = max(
        0.0,
        (settings["lexical_diversity_floor"] - lexical_diversity)
        / settings["lexical_diversity_floor"],
    )

    ratio_signal = min(
        repetition_ratio / settings["hard_ratio_threshold"],
        1.0,
    )
    frequency_signal = min(
        max(exact["maximum_count"] - settings["minimum_repeat_count"] + 1, 0)
        / 3,
        1.0,
    )
    structural_signal = min(
        structural_ratio / settings["hard_ratio_threshold"],
        1.0,
    )
    opening_signal = min(opening_ratio / 0.20, 1.0)
    repetition_score = min(
        1.0,
        (0.60 * ratio_signal)
        + (0.20 * frequency_signal)
        + (0.10 * structural_signal)
        + (0.07 * opening_signal)
        + (0.03 * lexical_penalty),
    )

    strong_signals = sum(
        (
            exact_ratio >= 0.20,
            structural_ratio >= 0.25,
            opening_ratio >= 0.12,
            exact["maximum_count"] >= settings["minimum_repeat_count"] + 1,
            lexical_penalty >= 0.40,
        )
    )
    long_enough = word_count >= settings["minimum_words"]
    dominant_exact = (
        exact_ratio >= settings["dominant_exact_ratio_threshold"]
        and exact["maximum_count"] >= settings["minimum_repeat_count"]
    )
    is_repetitive = long_enough and (
        dominant_exact
        or (
            repetition_ratio >= settings["hard_ratio_threshold"]
            and repetition_score >= settings["hard_score_threshold"]
            and strong_signals >= 2
        )
    )
    is_moderate = not is_repetitive and (
        repetition_ratio >= settings["moderate_ratio_threshold"]
        or repetition_score >= settings["moderate_score_threshold"]
    )

    if is_repetitive:
        status = "hard_zero"
        reason = (
            "Large portion of answer consists of repeated descriptive "
            "patterns or template-like sentence structures."
        )
    elif is_moderate:
        status = "moderate"
        reason = "Noticeable repetition was detected but did not meet the zero threshold."
    elif not long_enough:
        status = "pass"
        reason = "Answer is below the minimum length for a repetition-based zero."
    else:
        status = "pass"
        reason = "Repetition remained within the configured natural-answer limits."

    return {
        "detector_version": DETECTOR_VERSION,
        "answer_type": str(answer_type or ""),
        "profile": settings["profile"],
        "status": status,
        "is_repetitive": is_repetitive,
        "repetition_score": round(repetition_score, 4),
        "repetition_ratio": round(repetition_ratio, 4),
        "exact_repetition_ratio": round(exact_ratio, 4),
        "structural_repetition_ratio": round(structural_ratio, 4),
        "opening_repetition_ratio": round(opening_ratio, 4),
        "lexical_diversity": round(lexical_diversity, 4),
        "word_count": word_count,
        "minimum_words_for_zero": settings["minimum_words"],
        "repeated_phrases": exact["phrases"],
        "repeated_openings": openings["openings"],
        "similar_sentence_groups": structure["groups"],
        "reason": reason,
    }


def apply_repetition_score_override(evaluation_result, detection):
    """Attach detector evidence and zero validated criterion scores when required."""
    result = deepcopy(evaluation_result)
    checks = result.setdefault("integrity_checks", {})
    checks["repetition"] = deepcopy(detection)

    if not detection.get("is_repetitive"):
        return result

    evaluation = result.get("evaluation")
    if not isinstance(evaluation, dict):
        return result
    scores = evaluation.get("scores")
    if not isinstance(scores, dict) or not scores:
        return result

    overrides = result.get("score_overrides")
    if not isinstance(overrides, list):
        overrides = []
    existing_override = next(
        (
            item
            for item in overrides
            if isinstance(item, Mapping) and item.get("code") == OVERRIDE_CODE
        ),
        None,
    )
    original_scores = deepcopy(
        existing_override.get("original_scores", scores)
        if existing_override
        else scores
    )
    original_weighted_score = (
        existing_override.get(
            "original_weighted_score",
            evaluation.get("weighted_score"),
        )
        if existing_override
        else evaluation.get("weighted_score")
    )
    for payload in scores.values():
        if isinstance(payload, dict):
            payload["score"] = 0.0
    evaluation["weighted_score"] = 0.0

    overrides = [
        item
        for item in overrides
        if not isinstance(item, Mapping) or item.get("code") != OVERRIDE_CODE
    ]
    overrides.append({
        "code": OVERRIDE_CODE,
        "applied": True,
        "detector_version": detection.get("detector_version"),
        "reason": detection.get("reason"),
        "original_weighted_score": original_weighted_score,
        "original_scores": original_scores,
    })
    result["score_overrides"] = overrides
    return result


def _resolved_config(answer_type, profile, config):
    supplied = config if isinstance(config, Mapping) else {}
    answer_types = supplied.get("answer_types")
    if not isinstance(answer_types, Mapping):
        answer_types = {}
    selected_profile = (
        answer_types.get(answer_type)
        or profile
        or ANSWER_TYPE_PROFILES.get(answer_type)
        or "default"
    )
    resolved = dict(DEFAULT_CONFIG)
    resolved.update(PROFILE_OVERRIDES.get(selected_profile, {}))
    defaults = supplied.get("defaults")
    if isinstance(defaults, Mapping):
        resolved.update(defaults)
    profiles = supplied.get("profiles")
    if isinstance(profiles, Mapping):
        profile_values = profiles.get(selected_profile)
        if isinstance(profile_values, Mapping):
            resolved.update(profile_values)
    if "enabled" in supplied:
        resolved["enabled"] = bool(supplied["enabled"])
    resolved["profile"] = selected_profile
    return resolved


def _normalize_text(text):
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    return normalized.casefold().replace("\u2019", "'").replace("\u2018", "'")


def _tokenize(value):
    return TOKEN_RE.findall(value)


def _tokenize_with_sentences(text):
    tokens = []
    sentence_ranges = []
    for chunk in SENTENCE_BOUNDARY_RE.split(text):
        sentence_tokens = _tokenize(chunk)
        if not sentence_tokens:
            continue
        start = len(tokens)
        tokens.extend(sentence_tokens)
        sentence_ranges.append((start, len(tokens)))
    if not sentence_ranges and tokens:
        sentence_ranges.append((0, len(tokens)))
    return tokens, sentence_ranges


def _exact_repetition(tokens, sentence_ranges, settings):
    candidates = []
    for size in range(
        settings["maximum_phrase_words"],
        settings["minimum_phrase_words"] - 1,
        -1,
    ):
        occurrences = defaultdict(list)
        for sentence_start, sentence_end in sentence_ranges:
            for start in range(sentence_start, sentence_end - size + 1):
                occurrences[tuple(tokens[start:start + size])].append(start)
        for phrase, starts in occurrences.items():
            selected = _non_overlapping(starts, size)
            if len(selected) >= settings["minimum_repeat_count"]:
                candidates.append((size, phrase, selected))

    positions = set()
    phrases = []
    maximum_count = 0
    for size, phrase, starts in sorted(
        candidates,
        key=lambda item: (-item[0], -len(item[2]), item[1]),
    ):
        repeated = {
            index
            for start in starts
            for index in range(start, start + size)
        }
        newly_covered = repeated - positions
        if positions and len(newly_covered) / len(repeated) < 0.50:
            continue
        positions.update(repeated)
        maximum_count = max(maximum_count, len(starts))
        phrases.append({
            "phrase": " ".join(phrase),
            "count": len(starts),
            "word_count": size,
        })
        if len(phrases) >= 10:
            break

    return {
        "positions": positions,
        "phrases": phrases,
        "maximum_count": maximum_count,
    }


def _repeated_openings(tokens, sentence_ranges, settings):
    width = settings["starter_words"]
    occurrences = defaultdict(list)
    for start, end in sentence_ranges:
        if end - start >= width + 2:
            occurrences[tuple(tokens[start:start + width])].append(start)

    positions = set()
    openings = []
    for opening, starts in sorted(occurrences.items()):
        if len(starts) < settings["minimum_repeat_count"]:
            continue
        for start in starts:
            positions.update(range(start, start + width))
        openings.append({
            "phrase": " ".join(opening),
            "count": len(starts),
        })
    return {"positions": positions, "openings": openings[:10]}


def _similar_sentence_structure(tokens, sentence_ranges, settings):
    ranges = [
        item for item in sentence_ranges
        if item[1] - item[0] >= 6
    ][:settings["maximum_sentences"]]
    parent = list(range(len(ranges)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(ranges)):
        left_tokens = tokens[ranges[left][0]:ranges[left][1]]
        for right in range(left + 1, len(ranges)):
            right_tokens = tokens[ranges[right][0]:ranges[right][1]]
            length_ratio = min(len(left_tokens), len(right_tokens)) / max(
                len(left_tokens),
                len(right_tokens),
            )
            if length_ratio < 0.65:
                continue
            similarity = SequenceMatcher(None, left_tokens, right_tokens).ratio()
            if similarity >= settings["sentence_similarity_threshold"]:
                union(left, right)

    components = defaultdict(list)
    for index in range(len(ranges)):
        components[find(index)].append(index)

    positions = set()
    groups = []
    for members in components.values():
        if len(members) < settings["minimum_similar_sentences"]:
            continue
        for member in members:
            start, end = ranges[member]
            positions.update(range(start, end))
        groups.append({
            "sentence_numbers": [member + 1 for member in members],
            "count": len(members),
        })
    groups.sort(key=lambda item: (-item["count"], item["sentence_numbers"]))
    return {"positions": positions, "groups": groups[:10]}


def _non_overlapping(starts, width):
    selected = []
    next_available = -1
    for start in sorted(starts):
        if start >= next_available:
            selected.append(start)
            next_available = start + width
    return selected


def _moving_lexical_diversity(tokens, window_size=40):
    if not tokens:
        return 0.0
    if len(tokens) <= window_size:
        return len(set(tokens)) / len(tokens)
    windows = []
    step = window_size // 2
    for start in range(0, len(tokens) - window_size + 1, step):
        window = tokens[start:start + window_size]
        windows.append(len(set(window)) / window_size)
    return sum(windows) / len(windows)


def _result(*, answer_type, word_count, minimum_words, status, reason, profile):
    return {
        "detector_version": DETECTOR_VERSION,
        "answer_type": str(answer_type or ""),
        "profile": profile,
        "status": status,
        "is_repetitive": False,
        "repetition_score": 0.0,
        "repetition_ratio": 0.0,
        "exact_repetition_ratio": 0.0,
        "structural_repetition_ratio": 0.0,
        "opening_repetition_ratio": 0.0,
        "lexical_diversity": 0.0,
        "word_count": word_count,
        "minimum_words_for_zero": minimum_words,
        "repeated_phrases": [],
        "repeated_openings": [],
        "similar_sentence_groups": [],
        "reason": reason,
    }
