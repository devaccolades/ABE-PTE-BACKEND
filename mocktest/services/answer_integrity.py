from django.conf import settings

from examinor.scoring.task_contracts import TASK_CONTRACTS, get_task_contract
from examinor.services.known_answer_templates import (
    detect_known_template_answer,
)
from examinor.services.repetitive_answer import detect_repetitive_answer
from mocktest.models import AnswerTemplate


SUPPORTED_ANSWER_TYPES = tuple(
    name
    for name, contract in TASK_CONTRACTS.items()
    if contract.repetition_profile
)


def inspect_answer_integrity(text, answer_type):
    """Run the same deterministic text gates used before score compilation."""
    contract = get_task_contract(answer_type)
    if not contract.repetition_profile:
        raise ValueError(
            f"Answer type {answer_type!r} does not use descriptive-text gates."
        )

    repetition_config = getattr(settings, "REPETITIVE_ANSWER_CONFIG", {})
    repetition = detect_repetitive_answer(
        text,
        answer_type=answer_type,
        profile=contract.repetition_profile,
        config=repetition_config,
    )

    template_config = getattr(settings, "KNOWN_TEMPLATE_CONFIG", {})
    template_enabled = not (
        isinstance(template_config, dict)
        and template_config.get("enabled") is False
    )
    templates = (
        AnswerTemplate.objects.filter(
            answer_type=answer_type,
            is_active=True,
        )
        if template_enabled
        else ()
    )
    known_template = detect_known_template_answer(
        text,
        templates,
        answer_type=answer_type,
        config=template_config,
    )

    checks = {
        "repetition": _check_result(
            repetition,
            trigger_field="is_repetitive",
        ),
        "known_template": _check_result(
            known_template,
            trigger_field="is_template_dominated",
        ),
    }
    blocked_by = [
        name
        for name, check in checks.items()
        if check["blocked"]
    ]

    return {
        "answer_type": answer_type,
        "applicable": True,
        "decision": "blocked" if blocked_by else "pass",
        "passes": not blocked_by,
        "would_score_zero": bool(blocked_by),
        "blocked_by": blocked_by,
        "checks": checks,
        "scope_note": (
            "This diagnostic runs deterministic text-integrity gates only. "
            "It does not call AI or predict rubric scores."
        ),
    }


def _check_result(detection, *, trigger_field):
    blocked = bool(detection.get(trigger_field))
    return {
        "enabled": detection.get("status") != "disabled",
        "status": detection.get("status", "pass"),
        "passes": not blocked,
        "blocked": blocked,
        "reason": detection.get("reason", ""),
        "evidence": detection,
    }
