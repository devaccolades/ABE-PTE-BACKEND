from collections import defaultdict
from collections.abc import Mapping

from examinor.scoring.contracts import (
    SCORING_VERSION,
    VALID_SKILLS,
    CompiledSkillScore,
    CriterionScore,
    ScoringContractError,
    decimal_value,
)


def compile_skill_scores(
    criterion_scores,
    trait_skill_map,
    skill_maxima,
    *,
    gate_traits=(),
):
    """Compile validated rubric criterion scores into question skill scores."""
    criteria = _normalize_criteria(criterion_scores)
    mappings = _normalize_trait_skill_map(trait_skill_map, criteria)
    criteria_by_skill = _criteria_by_skill(criteria, mappings)
    maxima = _normalize_skill_maxima(skill_maxima, criteria_by_skill)
    gate_traits = _normalize_gate_traits(gate_traits, criteria)
    triggered_by = tuple(
        trait for trait in gate_traits if criteria[trait].score == 0
    )

    compiled = {}
    for skill in sorted(criteria_by_skill):
        mapped_criteria = criteria_by_skill[skill]
        criterion_score = sum(
            (criterion.score for criterion in mapped_criteria),
            start=decimal_value(0, "Criterion score total"),
        )
        criterion_maximum = sum(
            (criterion.maximum for criterion in mapped_criteria),
            start=decimal_value(0, "Criterion maximum total"),
        )
        ratio = criterion_score / criterion_maximum
        score = maxima[skill] * ratio
        if triggered_by:
            score = decimal_value(0, f"{skill} gated score")

        compiled[skill] = CompiledSkillScore(
            skill=skill,
            score=score,
            maximum=maxima[skill],
            ratio=ratio,
            criterion_score=criterion_score,
            criterion_maximum=criterion_maximum,
            criteria=tuple(
                criterion.criterion for criterion in mapped_criteria
            ),
        ).as_dict()

    return {
        "scoring_version": SCORING_VERSION,
        "criteria": [criteria[name].as_dict() for name in sorted(criteria)],
        "gate": {
            "traits": list(gate_traits),
            "triggered_by": list(triggered_by),
            "applied": bool(triggered_by),
        },
        "skills": compiled,
    }


def _normalize_criteria(criterion_scores):
    if not isinstance(criterion_scores, Mapping) or not criterion_scores:
        raise ScoringContractError("Criterion scores must be a non-empty object.")

    normalized = {}
    for name, payload in criterion_scores.items():
        criterion_name = str(name).strip()
        if criterion_name in normalized:
            raise ScoringContractError(
                f"Duplicate normalized criterion name: {criterion_name}"
            )
        normalized[criterion_name] = CriterionScore.from_payload(
            criterion_name,
            payload,
        )
    return normalized


def _normalize_trait_skill_map(trait_skill_map, criteria):
    if not isinstance(trait_skill_map, Mapping):
        raise ScoringContractError("Trait-to-skill map must be an object.")

    configured_mappings = {}
    for trait, configured in trait_skill_map.items():
        trait = str(trait).strip()
        if trait in configured_mappings:
            raise ScoringContractError(
                f"Duplicate normalized trait mapping: {trait}"
            )
        configured_mappings[trait] = configured

    unknown_traits = sorted(set(configured_mappings) - set(criteria))
    if unknown_traits:
        raise ScoringContractError(
            "Trait-to-skill map contains unknown criteria: "
            + ", ".join(str(trait) for trait in unknown_traits)
        )

    normalized = {}
    for criterion_name in criteria:
        configured = configured_mappings.get(criterion_name)
        if isinstance(configured, str):
            configured = [configured]
        if not isinstance(configured, (list, tuple, set)) or not configured:
            raise ScoringContractError(
                f"Criterion '{criterion_name}' has no skill mapping."
            )

        skills = tuple(sorted({str(skill).strip() for skill in configured}))
        unknown_skills = sorted(set(skills) - VALID_SKILLS)
        if unknown_skills:
            raise ScoringContractError(
                f"Criterion '{criterion_name}' maps to unknown skills: "
                + ", ".join(unknown_skills)
            )
        normalized[criterion_name] = skills

    return normalized


def _criteria_by_skill(criteria, mappings):
    grouped = defaultdict(list)
    for criterion_name in sorted(criteria):
        for skill in mappings[criterion_name]:
            grouped[skill].append(criteria[criterion_name])
    return dict(grouped)


def _normalize_skill_maxima(skill_maxima, criteria_by_skill):
    if not isinstance(skill_maxima, Mapping):
        raise ScoringContractError("Question skill maxima must be an object.")

    normalized = {}
    seen_skills = set()
    for skill, value in skill_maxima.items():
        skill = str(skill).strip()
        if skill not in VALID_SKILLS:
            raise ScoringContractError(f"Unknown question skill maximum: {skill}")
        if skill in seen_skills:
            raise ScoringContractError(
                f"Duplicate normalized question skill maximum: {skill}"
            )
        seen_skills.add(skill)
        if value is None:
            continue

        maximum = decimal_value(value, f"Question {skill} maximum")
        if maximum < 0:
            raise ScoringContractError(
                f"Question {skill} maximum cannot be negative."
            )
        if maximum > 0:
            normalized[skill] = maximum

    missing = sorted(set(criteria_by_skill) - set(normalized))
    if missing:
        raise ScoringContractError(
            "Missing positive question maxima for mapped skills: "
            + ", ".join(missing)
        )

    extra = sorted(set(normalized) - set(criteria_by_skill))
    if extra:
        raise ScoringContractError(
            "Question maxima have no mapped criteria: " + ", ".join(extra)
        )
    return normalized


def _normalize_gate_traits(gate_traits, criteria):
    if isinstance(gate_traits, str):
        gate_traits = [gate_traits]
    if not isinstance(gate_traits, (list, tuple, set)):
        raise ScoringContractError("Gate traits must be a list of criterion names.")

    normalized = tuple(sorted({str(trait).strip() for trait in gate_traits}))
    unknown = sorted(set(normalized) - set(criteria))
    if unknown:
        raise ScoringContractError(
            "Gate policy references unknown criteria: " + ", ".join(unknown)
        )
    return normalized
