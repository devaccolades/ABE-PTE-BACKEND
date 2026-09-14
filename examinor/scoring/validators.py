from copy import deepcopy
import re


LANGUAGE_ERROR_TYPES = ("grammar", "spelling")


def rubric_maxima(rubric):
    maxima = {}

    for key, value in (rubric or {}).items():
        max_score = 1

        if isinstance(value, dict):
            max_score = value.get("max") or value.get("max_score")
            if max_score is None:
                numeric_keys = [int(k) for k in value.keys() if str(k).isdigit()]
                max_score = max(numeric_keys) if numeric_keys else 1
        elif isinstance(value, list):
            max_score = len(value)

        try:
            maxima[str(key)] = float(max_score)
        except (TypeError, ValueError):
            maxima[str(key)] = 1.0

    return maxima


def validate_and_normalize_evaluation_result(evaluation_result, rubric=None):
    if not isinstance(evaluation_result, dict):
        return False, None, "Evaluation result must be an object."

    if not evaluation_result.get("ok", False):
        return False, None, evaluation_result.get("error", "Evaluation was not successful.")

    evaluation = evaluation_result.get("evaluation")
    if not isinstance(evaluation, dict):
        return False, None, "Evaluation payload must be an object."

    scores = evaluation.get("scores")
    if not isinstance(scores, dict) or not scores:
        return False, None, "Evaluation scores must be a non-empty object."

    expected_maxima = rubric_maxima(rubric)
    score_keys = {str(key) for key in scores.keys()}
    expected_keys = set(expected_maxima.keys())

    if expected_keys:
        missing = sorted(expected_keys - score_keys)
        extra = sorted(score_keys - expected_keys)
        if missing:
            return False, None, f"Evaluation missing rubric score keys: {', '.join(missing)}"
        if extra:
            return False, None, f"Evaluation returned unexpected score keys: {', '.join(extra)}"

    normalized = deepcopy(evaluation_result)
    normalized_scores = {}

    for key, payload in scores.items():
        key = str(key)
        if not isinstance(payload, dict):
            return False, None, f"Score payload for '{key}' must be an object."

        if "score" not in payload:
            return False, None, f"Score payload for '{key}' is missing score."

        try:
            score = float(payload.get("score"))
        except (TypeError, ValueError):
            return False, None, f"Score for '{key}' must be numeric."

        if expected_maxima:
            max_score = expected_maxima[key]
        else:
            try:
                max_score = float(payload.get("max"))
            except (TypeError, ValueError):
                return False, None, f"Max score for '{key}' must be numeric."

        if score < 0:
            return False, None, f"Score for '{key}' cannot be negative."
        if score > max_score:
            return False, None, f"Score for '{key}' exceeds max score."

        normalized_scores[key] = {
            **payload,
            "score": score,
            "max": max_score,
        }

    normalized["evaluation"]["scores"] = normalized_scores
    normalized["evaluation"]["max_score"] = sum(item["max"] for item in normalized_scores.values())
    normalized["evaluation"]["weighted_score"] = sum(item["score"] for item in normalized_scores.values())

    return True, normalized, None


def validate_and_normalize_language_feedback(evaluation_result, answer_text):
    """Validate candidate-facing language annotations against the saved answer."""
    normalized = deepcopy(evaluation_result)
    evaluation = normalized.get("evaluation")
    if not isinstance(evaluation, dict):
        return False, None, "Evaluation payload must be an object."

    scores = evaluation.get("scores")
    if not isinstance(scores, dict):
        return False, None, "Evaluation scores must be an object."

    feedback = evaluation.get("feedback")
    if not isinstance(feedback, dict):
        return False, None, "Language evaluation feedback must be an object."

    raw_errors = feedback.get("errors")
    if not isinstance(raw_errors, list):
        return False, None, "Language evaluation feedback.errors must be a list."

    answer_text = str(answer_text or "")
    errors = []
    seen = set()
    for index, item in enumerate(raw_errors, start=1):
        if not isinstance(item, dict):
            return False, None, f"Language error {index} must be an object."

        error_type = str(item.get("type") or "").strip().lower()
        if error_type not in LANGUAGE_ERROR_TYPES:
            return (
                False,
                None,
                f"Language error {index} has unsupported type {error_type!r}.",
            )

        error_text = str(item.get("text") or item.get("original") or "").strip()
        error_text = _exact_error_text(error_text, answer_text)
        if not error_text:
            return (
                False,
                None,
                f"Language error {index} is not an exact substring of the candidate response.",
            )

        key = (error_type, error_text)
        if key in seen:
            continue
        seen.add(key)
        errors.append({
            **item,
            "type": error_type,
            "text": error_text,
            "suggestion": str(item.get("suggestion") or "").strip(),
            "explanation": str(item.get("explanation") or "").strip(),
        })

    errors = _add_terminal_punctuation_error(answer_text, errors)

    for error_type in LANGUAGE_ERROR_TYPES:
        payload = scores.get(error_type)
        if not isinstance(payload, dict):
            continue
        score = float(payload.get("score") or 0)
        maximum = float(payload.get("max", payload.get("maximum")) or 0)
        has_errors = any(item["type"] == error_type for item in errors)
        if score < maximum and not has_errors:
            return (
                False,
                None,
                f"{error_type.title()} is below maximum but has no matching annotation.",
            )
        if error_type == "spelling" and maximum > 0 and score >= maximum and has_errors:
            return (
                False,
                None,
                f"{error_type.title()} is at maximum but matching errors were reported.",
            )

    normalized["evaluation"]["feedback"]["errors"] = errors
    return True, normalized, None


def _add_terminal_punctuation_error(answer_text, errors):
    stripped = answer_text.rstrip()
    if not stripped:
        return errors
    if stripped[-1] in ".!?":
        return errors
    if len(stripped) > 1 and stripped[-1] in "\"'”’" and stripped[-2] in ".!?":
        return errors

    for item in errors:
        text = item["text"]
        start = stripped.rfind(text)
        if item["type"] == "grammar" and start >= 0 and start + len(text) == len(stripped):
            return errors

    match = re.search(r"\S+$", stripped)
    if not match:
        return errors
    text = match.group(0)
    return [
        *errors,
        {
            "type": "grammar",
            "text": text,
            "suggestion": f"{text}.",
            "explanation": "The final sentence is missing terminal punctuation.",
        },
    ]


def _exact_error_text(error_text, answer_text):
    if not error_text:
        return ""
    if error_text in answer_text:
        return error_text

    quote_pairs = (("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’"))
    for opening, closing in quote_pairs:
        if error_text.startswith(opening) and error_text.endswith(closing):
            unquoted = error_text[len(opening):-len(closing)].strip()
            if unquoted and unquoted in answer_text:
                return unquoted
    return ""
