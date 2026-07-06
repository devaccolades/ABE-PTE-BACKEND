from copy import deepcopy


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
