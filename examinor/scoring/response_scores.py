from django.conf import settings

from examinor.scoring.contracts import SCORING_VERSION, VALID_SKILLS
from examinor.scoring.score_calculator import compile_skill_scores
from examinor.scoring.task_contracts import get_task_contract


SCORING_MODES = frozenset({"legacy", "shadow", "v2"})
LEGACY_SCORING_VERSION = "pte-score-v1"


class ResponseScoringError(ValueError):
    """Raised when response evidence cannot be promoted under the selected mode."""


def configured_scoring_mode():
    mode = str(getattr(settings, "EVALUATION_SCORING_MODE", "shadow")).strip().lower()
    if mode not in SCORING_MODES:
        raise ResponseScoringError(
            f"Unsupported EVALUATION_SCORING_MODE '{mode}'. "
            f"Expected one of: {', '.join(sorted(SCORING_MODES))}."
        )
    return mode


def compile_response_score_evidence(question, evaluation_result, *, mode=None):
    mode = configured_scoring_mode() if mode is None else str(mode).strip().lower()
    if mode not in SCORING_MODES:
        raise ResponseScoringError(f"Unsupported scoring mode: {mode}")

    scores = _criterion_scores(evaluation_result)
    trait_skill_map = question.subsection.trait_skill_map or {}
    skill_maxima = _skill_maxima(question)
    legacy = compile_legacy_skill_scores(scores, trait_skill_map, skill_maxima)

    evidence = {
        "mode": mode,
        "promoted_version": LEGACY_SCORING_VERSION,
        "legacy": legacy,
        "v2": None,
        "v2_error": "",
        "delta": {},
    }

    if mode in {"shadow", "v2"}:
        try:
            contract = get_task_contract(question.subsection.name)
            v2 = compile_skill_scores(
                scores,
                trait_skill_map,
                _mapped_skill_maxima(scores, trait_skill_map, skill_maxima),
                gate_traits=contract.gate_traits,
            )
        except (TypeError, ValueError) as exc:
            evidence["v2_error"] = str(exc)
            if mode == "v2":
                raise ResponseScoringError(
                    f"V2 score compilation failed: {exc}"
                ) from exc
        else:
            evidence["v2"] = v2
            evidence["delta"] = _score_delta(legacy, v2)
            if mode == "v2":
                evidence["promoted_version"] = SCORING_VERSION

    promoted = evidence["v2"] if mode == "v2" else legacy
    evidence["promoted"] = promoted
    return evidence


def compile_legacy_skill_scores(scores, trait_skill_map, skill_maxima):
    gated_by = sorted(
        trait
        for trait in ("content", "form")
        if trait in scores and float(scores[trait]["score"]) == 0
    )
    raw_scores = {skill: 0.0 for skill in VALID_SKILLS}

    if not gated_by:
        for criterion, payload in scores.items():
            value = float(payload["score"])
            configured = trait_skill_map.get(criterion, [])
            for skill in configured:
                if skill in raw_scores:
                    raw_scores[skill] += value

    skills = {}
    for skill in sorted(VALID_SKILLS):
        maximum = float(skill_maxima.get(skill) or 0)
        score = min(raw_scores[skill], maximum) if maximum else 0.0
        skills[skill] = {
            "score": score,
            "maximum": maximum,
        }

    return {
        "scoring_version": LEGACY_SCORING_VERSION,
        "gate": {
            "traits": [trait for trait in ("content", "form") if trait in scores],
            "triggered_by": gated_by,
            "applied": bool(gated_by),
        },
        "skills": skills,
    }


def promoted_skill_values(evidence):
    skills = evidence["promoted"]["skills"]
    return {
        skill: float(skills.get(skill, {}).get("score", 0))
        for skill in VALID_SKILLS
    }


def _criterion_scores(evaluation_result):
    if not isinstance(evaluation_result, dict):
        raise ResponseScoringError("Evaluation result must be an object.")
    scores = evaluation_result.get("evaluation", {}).get("scores")
    if not isinstance(scores, dict) or not scores:
        raise ResponseScoringError("Evaluation result has no criterion scores.")
    return scores


def _skill_maxima(question):
    return {
        skill: getattr(question, f"{skill}_score_max") or 0
        for skill in VALID_SKILLS
    }


def _mapped_skill_maxima(scores, trait_skill_map, skill_maxima):
    mapped = set()
    for criterion in scores:
        configured = trait_skill_map.get(criterion, [])
        if isinstance(configured, str):
            configured = [configured]
        mapped.update(skill for skill in configured if skill in VALID_SKILLS)
    return {skill: skill_maxima.get(skill) for skill in mapped}


def _score_delta(legacy, v2):
    delta = {}
    for skill in sorted(VALID_SKILLS):
        legacy_score = float(legacy["skills"].get(skill, {}).get("score", 0))
        v2_score = float(v2["skills"].get(skill, {}).get("score", 0))
        delta[skill] = v2_score - legacy_score
    return delta
