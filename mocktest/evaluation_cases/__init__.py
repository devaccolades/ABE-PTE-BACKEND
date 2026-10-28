"""Student-submission cases that pin down how each question type should be evaluated.

Run them with ``python manage.py run_evaluation_cases``; see docs/EVALUATION_CASES.md.
"""

from . import listening, reading, speaking, writing
from .schema import EvaluationCase, KeyAnswer

CASES = [*speaking.CASES, *writing.CASES, *reading.CASES, *listening.CASES]

__all__ = ["CASES", "EvaluationCase", "KeyAnswer"]
