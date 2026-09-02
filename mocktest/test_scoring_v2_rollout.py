from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    Section,
    SubSection,
    UserMockTestSession,
    UserResponse,
)


@override_settings(EVALUATION_SCORING_MODE="shadow")
class ScoringV2RolloutCommandTests(TestCase):
    def setUp(self):
        self.mock_test = MockTest.objects.create(
            title="Canary Test",
            scoring_mode="shadow",
        )
        MockTest.objects.filter(pk=self.mock_test.pk).update(is_active=True)
        self.mock_test.refresh_from_db()
        section = Section.objects.create(name="Reading")
        test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=section,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="mc_single",
            evaluation_type="rule",
            rubric={"reading": {"0": "Wrong", "1": "Correct"}},
            trait_skill_map={"reading": ["reading"]},
        )
        self.question = Question.objects.create(
            mock_test_section=test_section,
            subsection=subsection,
            name="Reading question",
            text="Choose one.",
            reading_score_max=1,
        )
        QuestionOption.objects.create(
            question=self.question,
            option_text="Correct",
            is_correct=True,
        )
        self.session = UserMockTestSession.objects.create(
            name="Existing candidate",
            session_id="existing-shadow-session",
            mock_test=self.mock_test,
            scoring_mode="shadow",
        )
        self.response = UserResponse.objects.create(
            user_session=self.session,
            mock_test=self.mock_test,
            question=self.question,
            evaluated=True,
            evaluation_status="completed",
            evaluation_result={
                "evaluation": {
                    "scores": {"reading": {"score": 1, "max": 1}},
                },
            },
            reading_score_awarded=1,
        )

    @patch(
        "mocktest.management.commands.rollout_mock_test_scoring_v2.publication_errors",
        return_value=[],
    )
    def test_dry_run_does_not_change_mock_test_or_session(self, _publication):
        stdout = StringIO()

        call_command(
            "rollout_mock_test_scoring_v2",
            self.mock_test.title,
            stdout=stdout,
        )

        self.mock_test.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(self.mock_test.scoring_mode, "shadow")
        self.assertEqual(self.session.scoring_mode, "shadow")
        self.assertIn("Dry run only", stdout.getvalue())

    @patch(
        "mocktest.management.commands.rollout_mock_test_scoring_v2.publication_errors",
        return_value=[],
    )
    def test_confirm_requires_exact_production_counts(self, _publication):
        with self.assertRaisesMessage(CommandError, "Session Count changed"):
            self._confirm(expected_session_count=2)

        self.mock_test.refresh_from_db()
        self.assertEqual(self.mock_test.scoring_mode, "shadow")

    @patch(
        "mocktest.management.commands.rollout_mock_test_scoring_v2.publication_errors",
        return_value=[],
    )
    def test_confirm_promotes_only_future_sessions(self, _publication):
        stdout = self._confirm()

        self.mock_test.refresh_from_db()
        self.session.refresh_from_db()
        self.response.refresh_from_db()
        self.assertEqual(self.mock_test.scoring_mode, "v2")
        self.assertEqual(self.session.scoring_mode, "shadow")
        self.assertEqual(self.response.reading_score_awarded, 1)
        self.assertIn("no response or session score was changed", stdout.getvalue())

        future = UserMockTestSession.objects.create(
            name="Future candidate",
            session_id="future-v2-session",
            mock_test=self.mock_test,
            scoring_mode=self.mock_test.scoring_mode,
        )
        self.assertEqual(future.scoring_mode, "v2")

    @patch(
        "mocktest.management.commands.rollout_mock_test_scoring_v2.publication_errors",
        return_value=[],
    )
    def test_confirm_requires_explicit_policy_warning_acknowledgement(
        self,
        _publication,
    ):
        Question.objects.filter(pk=self.question.pk).update(reading_score_max=2)

        with self.assertRaisesMessage(
            CommandError,
            "require --acknowledge-policy-warnings",
        ):
            self._confirm(expected_reference_difference_count=1)

        self.mock_test.refresh_from_db()
        self.assertEqual(self.mock_test.scoring_mode, "shadow")

    def _confirm(
        self,
        *,
        expected_session_count=1,
        expected_reference_difference_count=0,
    ):
        stdout = StringIO()
        call_command(
            "rollout_mock_test_scoring_v2",
            self.mock_test.title,
            "--expected-question-count",
            "1",
            "--expected-session-count",
            str(expected_session_count),
            "--expected-user-response-count",
            "1",
            "--expected-single-response-count",
            "0",
            "--expected-reference-difference-count",
            str(expected_reference_difference_count),
            "--expected-review-required-count",
            "0",
            "--reason",
            "Reviewed canary rollout",
            "--confirm",
            stdout=stdout,
        )
        return stdout
