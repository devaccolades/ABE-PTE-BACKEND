"""Case definitions and expectation checks for the evaluation case suite."""

from dataclasses import dataclass, field

from examinor.scoring.task_contracts import TASK_CONTRACTS


EXPECT_KEYS = frozenset({"status", "zero", "override", "no_override", "ratio", "traits"})
STATUSES = frozenset({"completed", "failed"})
RATIO_TOLERANCE = 1e-6


@dataclass(frozen=True)
class KeyAnswer:
    """An answer built at run time from the question's answer key, e.g. "correct"."""

    variant: str


@dataclass(frozen=True)
class EvaluationCase:
    """One student submission and the outcome company policy expects for it.

    expect keys (all optional; status defaults to "completed"):
      status       final SingleResponse status: "completed" or "failed"
      zero         True when the awarded skill score must be 0 (after the content/form
                   gate), False when it must be above 0
      override     applied score-override code that must be present
      no_override  True when no score override may be applied
      ratio        (low, high) inclusive bounds for total score / maximum
      traits       {trait: (low, high)} inclusive bounds on the raw trait score

    known_issue documents a current defect, so a failure is reported as known
    rather than as a regression. Delivery traits are never asserted for spoken
    tasks: cases supply a transcript without audio measurements.
    """

    id: str
    task: str
    question_id: int
    question_name: str
    label: str
    answer: object
    expect: dict = field(default_factory=dict)
    trainer_ref: str = ""
    known_issue: str = ""


@dataclass
class Observation:
    status: str
    error: str = ""
    scores: dict = field(default_factory=dict)
    overrides: tuple = ()
    integrity: dict = field(default_factory=dict)
    attempts: int = 0
    # Skill score the student receives; None when no score was awarded.
    awarded: float | None = None
    gated: bool = False

    @property
    def total(self):
        return sum(score for score, _ in self.scores.values())

    @property
    def maximum(self):
        return sum(maximum for _, maximum in self.scores.values())


def observe(response):
    """Summarise a SingleResponse after its evaluation task has finished."""
    result = response.evaluation_result or {}
    evaluation = result.get("evaluation") or {}
    scores = {
        trait: (float(payload.get("score") or 0), float(payload.get("max") or 0))
        for trait, payload in (evaluation.get("scores") or {}).items()
        if isinstance(payload, dict)
    }
    overrides = tuple(
        item.get("code")
        for item in result.get("score_overrides") or []
        if isinstance(item, dict) and item.get("applied")
    )
    integrity = {
        name: check.get("status")
        for name, check in (result.get("integrity_checks") or {}).items()
        if isinstance(check, dict)
    }
    error = response.evaluation_error or ""
    if result.get("code"):
        error = f"[{result['code']}] {error}"
    promoted = (result.get("scoring_evidence") or {}).get("promoted") or {}
    awarded = None
    if promoted:
        awarded = sum(
            getattr(response, f"{skill}_score_awarded")
            for skill in ("speaking", "writing", "reading", "listening")
        )
    return Observation(
        status=response.evaluation_status,
        error=error,
        scores=scores,
        overrides=overrides,
        integrity=integrity,
        attempts=response.evaluation_attempts,
        awarded=awarded,
        gated=bool((promoted.get("gate") or {}).get("applied")),
    )


def check_expectations(expect, observation):
    """Return a list of human-readable expectation failures (empty when met)."""
    expected_status = expect.get("status", "completed")
    if observation.status != expected_status:
        detail = f": {observation.error}" if observation.error else ""
        return [f"status {observation.status}, expected {expected_status}{detail}"]
    if expected_status != "completed":
        return []

    failures = []
    total, maximum = observation.total, observation.maximum
    awarded = total if observation.awarded is None else observation.awarded
    if "zero" in expect and (awarded == 0) != expect["zero"]:
        failures.append(
            f"awarded {round(awarded, 2):g} (traits {total:g}/{maximum:g}), expected "
            + ("zero" if expect["zero"] else "a nonzero score")
        )
    if "override" in expect and expect["override"] not in observation.overrides:
        failures.append(
            f"override {expect['override']} not applied "
            f"(applied: {', '.join(observation.overrides) or 'none'})"
        )
    if expect.get("no_override") and observation.overrides:
        failures.append(f"unexpected override(s): {', '.join(observation.overrides)}")
    if "ratio" in expect:
        low, high = expect["ratio"]
        ratio = total / maximum if maximum else 0.0
        if not low - RATIO_TOLERANCE <= ratio <= high + RATIO_TOLERANCE:
            failures.append(f"score ratio {ratio:.2f} outside {low:g}-{high:g}")
    for trait, (low, high) in expect.get("traits", {}).items():
        if trait not in observation.scores:
            failures.append(f"trait {trait} missing from scores")
            continue
        score = observation.scores[trait][0]
        if not low <= score <= high:
            failures.append(f"{trait} {score:g} outside {low:g}-{high:g}")
    return failures


def validate_case(case):
    """Return definition problems; an empty list means the case is well formed."""
    problems = []
    if case.task not in TASK_CONTRACTS:
        problems.append(f"unknown task {case.task!r}")
    unknown = set(case.expect) - EXPECT_KEYS
    if unknown:
        problems.append(f"unknown expect keys {sorted(unknown)}")
    if case.expect.get("status", "completed") not in STATUSES:
        problems.append(f"invalid status {case.expect['status']!r}")
    bounds = [case.expect["ratio"]] if "ratio" in case.expect else []
    bounds += list(case.expect.get("traits", {}).values())
    for bound in bounds:
        if not (isinstance(bound, tuple) and len(bound) == 2 and bound[0] <= bound[1]):
            problems.append(f"invalid bound {bound!r}")
    if not case.expect:
        problems.append("no expectations")
    return problems
