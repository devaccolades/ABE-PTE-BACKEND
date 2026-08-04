from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


SCORING_VERSION = "pte-score-v2"
VALID_SKILLS = frozenset({"speaking", "writing", "reading", "listening"})


class ScoringContractError(ValueError):
    """Raised when normalized evaluation evidence cannot be scored safely."""


def decimal_value(value, label):
    if value is None or isinstance(value, bool):
        raise ScoringContractError(f"{label} must be a finite number.")

    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ScoringContractError(f"{label} must be a finite number.") from exc

    if not number.is_finite():
        raise ScoringContractError(f"{label} must be a finite number.")
    return number


def json_number(value):
    return float(value)


@dataclass(frozen=True, slots=True)
class CriterionScore:
    criterion: str
    score: Decimal
    maximum: Decimal

    def __post_init__(self):
        if not self.criterion:
            raise ScoringContractError("Criterion name cannot be empty.")
        if self.maximum <= 0:
            raise ScoringContractError(
                f"Criterion '{self.criterion}' maximum must be greater than zero."
            )
        if self.score < 0:
            raise ScoringContractError(
                f"Criterion '{self.criterion}' score cannot be negative."
            )
        if self.score > self.maximum:
            raise ScoringContractError(
                f"Criterion '{self.criterion}' score exceeds its maximum."
            )

    @classmethod
    def from_payload(cls, criterion, payload):
        criterion = str(criterion).strip()
        if not isinstance(payload, Mapping):
            raise ScoringContractError(
                f"Criterion '{criterion}' payload must be an object."
            )
        if "score" not in payload:
            raise ScoringContractError(
                f"Criterion '{criterion}' payload is missing score."
            )

        maximum_key = "maximum" if "maximum" in payload else "max"
        if maximum_key not in payload:
            raise ScoringContractError(
                f"Criterion '{criterion}' payload is missing maximum."
            )

        return cls(
            criterion=criterion,
            score=decimal_value(payload["score"], f"Criterion '{criterion}' score"),
            maximum=decimal_value(
                payload[maximum_key],
                f"Criterion '{criterion}' maximum",
            ),
        )

    def as_dict(self):
        return {
            "criterion": self.criterion,
            "score": json_number(self.score),
            "maximum": json_number(self.maximum),
        }


@dataclass(frozen=True, slots=True)
class CompiledSkillScore:
    skill: str
    score: Decimal
    maximum: Decimal
    ratio: Decimal
    criterion_score: Decimal
    criterion_maximum: Decimal
    criteria: tuple[str, ...]

    def as_dict(self):
        return {
            "score": json_number(self.score),
            "maximum": json_number(self.maximum),
            "ratio": json_number(self.ratio),
            "criterion_score": json_number(self.criterion_score),
            "criterion_maximum": json_number(self.criterion_maximum),
            "criteria": list(self.criteria),
        }
