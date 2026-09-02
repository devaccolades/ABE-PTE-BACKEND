from collections.abc import Mapping

from examinor.scoring.task_contracts import get_task_contract
from examinor.services.orchestrator import build_task_rubric


def build_evaluation_breakdown(response):
    """Build a candidate-safe explanation of the score already persisted."""
    if not response.evaluated or response.evaluation_status != "completed":
        return None

    result = response.evaluation_result
    if not isinstance(result, Mapping):
        return None

    evaluation = result.get("evaluation")
    evidence = result.get("scoring_evidence")
    if not isinstance(evaluation, Mapping) or not isinstance(evidence, Mapping):
        return None

    scores = evaluation.get("scores")
    promoted = evidence.get("promoted")
    if not isinstance(scores, Mapping) or not isinstance(promoted, Mapping):
        return None

    promoted_skills = promoted.get("skills")
    if not isinstance(promoted_skills, Mapping):
        return None

    question = response.question
    subsection = question.subsection
    trait_skill_map = subsection.trait_skill_map or {}
    rubric = build_task_rubric(subsection)
    criteria = _criteria_breakdown(scores, trait_skill_map, rubric)
    scoring_version = str(
        evidence.get("promoted_version")
        or promoted.get("scoring_version")
        or ""
    )
    skill_contributions = _skill_breakdown(
        promoted_skills,
        criteria,
        scoring_version=scoring_version,
    )

    awarded = sum(item["awarded"] for item in skill_contributions)
    maximum = sum(item["question_maximum"] for item in skill_contributions)
    gate = promoted.get("gate") if isinstance(promoted.get("gate"), Mapping) else {}
    evaluation_source = str(evaluation.get("evaluation_source") or "").strip()
    if not evaluation_source:
        evaluation_source = get_task_contract(
            subsection.name
        ).evaluation_engine.value

    return {
        "schema_version": "evaluation-breakdown-v1",
        "evaluation_source": evaluation_source,
        "scoring_mode": str(evidence.get("mode") or ""),
        "scoring_version": scoring_version,
        "maximum_source": "question_paper",
        "criteria": criteria,
        "skill_contributions": skill_contributions,
        "gate": {
            "applied": bool(gate.get("applied")),
            "triggered_by": [str(item) for item in gate.get("triggered_by", [])],
        },
        "combined": {
            "awarded": _number(awarded),
            "maximum": _number(maximum),
            "performance_percentage": _percentage(awarded, maximum),
        },
        "note": (
            "This is the question-level contribution. The final PTE score is "
            "calculated from the completed exam, not from one question."
        ),
    }


def _criteria_breakdown(scores, trait_skill_map, rubric):
    criteria = []
    for name in sorted(scores):
        payload = scores[name]
        if not isinstance(payload, Mapping):
            continue
        try:
            awarded = float(payload.get("score", 0))
            maximum = float(
                payload.get("maximum", payload.get("max", 0))
            )
        except (TypeError, ValueError):
            continue

        mapped_skills = trait_skill_map.get(name, [])
        if isinstance(mapped_skills, str):
            mapped_skills = [mapped_skills]
        if not isinstance(mapped_skills, (list, tuple, set)):
            mapped_skills = []

        criteria.append(
            {
                "name": str(name),
                "label": _label(name),
                "awarded": _number(awarded),
                "maximum": _number(maximum),
                "percentage": _percentage(awarded, maximum),
                "mapped_skills": sorted(str(skill) for skill in mapped_skills),
                "rubric": _rubric_details(rubric.get(name), awarded),
            }
        )
    return criteria


def _skill_breakdown(promoted_skills, criteria, *, scoring_version):
    criteria_by_name = {item["name"]: item for item in criteria}
    is_v2 = scoring_version == "pte-score-v2"
    contributions = []

    for skill in sorted(promoted_skills):
        payload = promoted_skills[skill]
        if not isinstance(payload, Mapping):
            continue
        awarded = _float(payload.get("score"))
        maximum = _float(payload.get("maximum"))
        if awarded == 0 and maximum == 0:
            continue

        criterion_names = payload.get("criteria")
        if not isinstance(criterion_names, list):
            criterion_names = [
                item["name"]
                for item in criteria
                if skill in item["mapped_skills"]
            ]
        mapped = [
            criteria_by_name[name]
            for name in criterion_names
            if name in criteria_by_name
        ]
        criterion_awarded = _float(
            payload.get(
                "criterion_score",
                sum(item["awarded"] for item in mapped),
            )
        )
        criterion_maximum = _float(
            payload.get(
                "criterion_maximum",
                sum(item["maximum"] for item in mapped),
            )
        )
        ratio = _float(
            payload.get(
                "ratio",
                criterion_awarded / criterion_maximum
                if criterion_maximum
                else 0,
            )
        )

        if is_v2:
            formula = (
                f"{_display(criterion_awarded)} / "
                f"{_display(criterion_maximum)} x {_display(maximum)} "
                f"= {_display(awarded)}"
            )
            method = "proportional"
        else:
            formula = (
                f"min({_display(criterion_awarded)}, "
                f"{_display(maximum)}) = {_display(awarded)}"
            )
            method = "legacy"

        contributions.append(
            {
                "skill": str(skill),
                "label": _label(skill),
                "criteria": [item["name"] for item in mapped],
                "criterion_awarded": _number(criterion_awarded),
                "criterion_maximum": _number(criterion_maximum),
                "ratio": _number(ratio),
                "percentage": _percentage(criterion_awarded, criterion_maximum),
                "question_maximum": _number(maximum),
                "awarded": _number(awarded),
                "method": method,
                "formula": formula,
            }
        )
    return contributions


def _rubric_details(config, awarded):
    if not isinstance(config, Mapping):
        return {"matched_descriptor": "", "bands": []}

    bands = []
    for key, value in config.items():
        try:
            score = float(key)
        except (TypeError, ValueError):
            continue
        description = _rubric_description(value)
        if description:
            bands.append(
                {
                    "score": _number(score),
                    "description": description,
                }
            )
    bands.sort(key=lambda item: item["score"])
    matched = next(
        (
            item["description"]
            for item in bands
            if abs(float(item["score"]) - awarded) < 0.000001
        ),
        "",
    )
    if not matched:
        matched = _rubric_description(config.get("description"))
    return {"matched_descriptor": matched, "bands": bands}


def _rubric_description(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("description", "label", "text"):
            if value.get(key):
                return str(value[key]).strip()
    return ""


def _float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _number(value):
    rounded = round(float(value), 4)
    return int(rounded) if rounded.is_integer() else rounded


def _percentage(awarded, maximum):
    return round((float(awarded) / float(maximum)) * 100, 2) if maximum else 0.0


def _display(value):
    return str(_number(value))


def _label(value):
    return str(value).replace("_", " ").strip().title()
