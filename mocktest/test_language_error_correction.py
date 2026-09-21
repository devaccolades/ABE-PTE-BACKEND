from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    Section,
    SubSection,
    UserMockTestSession,
    UserResponse,
)


class CorrectLanguageErrorClassificationTests(TestCase):
    def setUp(self):
        mock_test = MockTest.objects.create(title="Language correction test")
        section = Section.objects.create(name="Listening")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="summarize_spoken_text",
            rubric={
                "content": {"0": "Missing", "1": "Present"},
                "form": {"0": "Invalid", "1": "Valid"},
                "grammar": {"0": "Defective", "1": "Some errors", "2": "Correct"},
                "spelling": {"0": "Several", "1": "One", "2": "Correct"},
            },
            trait_skill_map={
                "content": ["writing"],
                "form": ["writing"],
                "grammar": ["writing"],
                "spelling": ["writing"],
            },
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="SST",
            writing_score_max=6,
        )
        self.session = UserMockTestSession.objects.create(
            name="Student",
            session_id="language-correction-session",
            mock_test=mock_test,
            scoring_mode="v2",
        )
        self.response = UserResponse.objects.create(
            user_session=self.session,
            mock_test=mock_test,
            question=question,
            evaluated=True,
            evaluation_status="completed",
            evaluation_result={
                "ok": True,
                "evaluation": {
                    "scores": {
                        "content": {"score": 1, "max": 1},
                        "form": {"score": 1, "max": 1},
                        "grammar": {"score": 1, "max": 2},
                        "spelling": {"score": 2, "max": 2},
                    },
                    "feedback": {
                        "errors": [
                            {
                                "type": "grammar",
                                "text": "taking about",
                                "suggestion": "talking about",
                                "explanation": "Incorrect word.",
                            },
                            {
                                "type": "grammar",
                                "text": "summary",
                                "suggestion": "summary.",
                                "explanation": "Missing punctuation.",
                            },
                        ]
                    },
                },
            },
            writing_score_awarded=5,
        )

    def _args(self):
        return (
            "--response-id", str(self.response.pk),
            "--question-id", str(self.response.question_id),
            "--error-text", "taking about",
            "--expected-suggestion", "talking about",
            "--expected-type", "grammar",
            "--new-type", "spelling",
            "--expected-grammar-score", "1",
            "--new-grammar-score", "1",
            "--expected-spelling-score", "2",
            "--new-spelling-score", "1",
        )

    def test_dry_run_does_not_change_response(self):
        stdout = StringIO()

        call_command(
            "correct_language_error_classification",
            *self._args(),
            stdout=stdout,
        )

        self.response.refresh_from_db()
        error = self.response.evaluation_result["evaluation"]["feedback"]["errors"][0]
        self.assertEqual(error["type"], "grammar")
        self.assertIn("grammar -> spelling", stdout.getvalue())
        self.assertIn("Dry run only", stdout.getvalue())

    def test_confirm_corrects_annotation_scores_and_session(self):
        stdout = StringIO()

        call_command(
            "correct_language_error_classification",
            *self._args(),
            "--reason", "Confirmed real-word typing error",
            "--confirm",
            stdout=stdout,
        )

        self.response.refresh_from_db()
        self.session.refresh_from_db()
        evaluation = self.response.evaluation_result["evaluation"]
        self.assertEqual(evaluation["feedback"]["errors"][0]["type"], "spelling")
        self.assertEqual(evaluation["scores"]["grammar"]["score"], 1)
        self.assertEqual(evaluation["scores"]["spelling"]["score"], 1)
        self.assertEqual(self.response.writing_score_awarded, 4)
        self.assertEqual(self.session.writing_score_awarded, 4)
        self.assertEqual(
            self.response.evaluation_result["evaluation_corrections"][-1]["reason"],
            "Confirmed real-word typing error",
        )
        self.assertIn("No AI provider was called", stdout.getvalue())

    def test_confirm_rejects_changed_score(self):
        self.response.evaluation_result["evaluation"]["scores"]["spelling"]["score"] = 1
        self.response.save(update_fields=["evaluation_result"])

        with self.assertRaisesMessage(CommandError, "Current spelling score is 1"):
            call_command(
                "correct_language_error_classification",
                *self._args(),
                "--reason", "Confirmed real-word typing error",
                "--confirm",
                stdout=StringIO(),
            )
