"""Deterministic caps on written-task scores, applied after rubric grading."""

from copy import deepcopy


# Pearson's Development, Structure and Coherence band 3: the essay "does not make
# effective use of paragraphs or lacks paragraphs". Higher bands require them.
NO_PARAGRAPHS_STRUCTURE_CAP = 3.0


def paragraph_count(answer):
    return sum(1 for line in str(answer or "").splitlines() if line.strip())


def apply_written_score_guardrails(evaluation, *, task_type, answer):
    scores = evaluation.get("scores") if isinstance(evaluation, dict) else None
    if not isinstance(scores, dict):
        return evaluation
    caps = []
    if task_type == "write_essay" and isinstance(scores.get("development_structure_coherence"), dict):
        paragraphs = paragraph_count(answer)
        if paragraphs < 2:
            caps.append(("development_structure_coherence", NO_PARAGRAPHS_STRUCTURE_CAP,
                         "no_paragraph_breaks", {"paragraphs": paragraphs}))
    if isinstance(scores.get("spelling"), dict):
        # Pearson spelling: 2 correct, 1 one error, 0 more than one. The count comes
        # from the validated spelling annotations the student is shown.
        feedback = evaluation.get("feedback")
        errors = feedback.get("errors") if isinstance(feedback, dict) else None
        count = sum(1 for item in errors or [] if isinstance(item, dict) and item.get("type") == "spelling")
        if count:
            caps.append(("spelling", 0.0 if count > 1 else 1.0, "spelling_error_count", {"spelling_errors": count}))

    result = None
    for criterion, cap, reason, evidence in caps:
        original = float(scores[criterion].get("score") or 0)
        if original <= cap:
            continue
        result = result or deepcopy(evaluation)
        result["scores"][criterion]["score"] = cap
        result["score_guardrails"] = [
            *result.get("score_guardrails", []),
            {"criterion": criterion, "original_score": original, "adjusted_score": cap,
             "reason": reason, "evidence": evidence},
        ]
    if result is None:
        return evaluation
    result["weighted_score"] = sum(
        float(payload.get("score") or 0)
        for payload in result["scores"].values()
        if isinstance(payload, dict)
    )
    return result
