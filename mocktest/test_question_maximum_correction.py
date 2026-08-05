from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    Section,
    SingleResponse,
    SubSection,
    UserMockTestSession,
    UserResponse,
)


@override_settings(EVALUATION_SCORING_MODE="shadow")
class CorrectQuestionSkillMaximumTests(TestCase):
    def setUp(self):
        mock_test = MockTest.objects.create(title="Weighted Test")
        section = Section.objects.create(name="Speaking")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="repeat_sentence",
            rubric={"content": {"0": "None", "3": "Complete"}},
            trait_skill_map={"content": ["listening"]},
        )
        self.question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="RS typo",
            listening_score_max=15,
        )
        self.session = UserMockTestSession.objects.create(
            name="Student",
            session_id="maximum-correction-session",
            mock_test=mock_test,
        )
        result = {
            "ok": True,
            "evaluation": {
                "scores": {"content": {"score": 2, "max": 3}},
            },
        }
        self.user_response = UserResponse.objects.create(
            user_session=self.session,
            mock_test=mock_test,
            question=self.question,
            evaluated=True,
            evaluation_status="completed",
            evaluation_result=result,
            listening_score_awarded=2,
        )
        self.single_response = SingleResponse.objects.create(
            question=self.question,
            evaluated=True,
            evaluation_status="completed",
            evaluation_result=result,
            listening_score_awarded=2,
        )

    def test_dry_run_reports_delta_without_writes(self):
        stdout = StringIO()

        call_command(
            "correct_question_skill_maximum",
            "--question-id",
            str(self.question.pk),
            "--skill",
            "listening",
            "--expected-current",
            "15",
            "--new-maximum",
            "1.5",
            stdout=stdout,
        )

        self.question.refresh_from_db()
        self.user_response.refresh_from_db()
        self.assertEqual(self.question.listening_score_max, 15)
        self.assertEqual(self.user_response.listening_score_awarded, 2)
        self.assertIn("proposed_listening=1.5", stdout.getvalue())
        self.assertIn("Dry run only", stdout.getvalue())

    def test_confirm_requires_exact_response_counts(self):
        with self.assertRaisesMessage(CommandError, "count changed"):
            call_command(
                "correct_question_skill_maximum",
                "--question-id",
                str(self.question.pk),
                "--skill",
                "listening",
                "--expected-current",
                "15",
                "--new-maximum",
                "1.5",
                "--reason",
                "Confirmed decimal typo",
                "--expected-user-count",
                "2",
                "--expected-single-count",
                "1",
                "--confirm",
                stdout=StringIO(),
            )

        self.question.refresh_from_db()
        self.assertEqual(self.question.listening_score_max, 15)

    def test_confirm_rescores_and_records_correction_history(self):
        stdout = StringIO()

        call_command(
            "correct_question_skill_maximum",
            "--question-id",
            str(self.question.pk),
            "--skill",
            "listening",
            "--expected-current",
            "15",
            "--new-maximum",
            "1.5",
            "--reason",
            "Confirmed decimal typo in RS question weight",
            "--expected-user-count",
            "1",
            "--expected-single-count",
            "1",
            "--confirm",
            stdout=stdout,
        )

        self.question.refresh_from_db()
        self.user_response.refresh_from_db()
        self.single_response.refresh_from_db()
        self.session.refresh_from_db()

        self.assertEqual(self.question.listening_score_max, 1.5)
        self.assertEqual(self.user_response.listening_score_awarded, 1.5)
        self.assertEqual(self.single_response.listening_score_awarded, 1.5)
        self.assertEqual(self.session.listening_score_awarded, 1.5)
        self.assertEqual(self.session.total_score, 90)
        correction = self.user_response.evaluation_result["score_corrections"][-1]
        self.assertEqual(correction["maximum_before"], 15)
        self.assertEqual(correction["maximum_after"], 1.5)
        self.assertEqual(correction["awarded_before"]["listening"], 2)
        self.assertEqual(correction["awarded_after"]["listening"], 1.5)
        self.assertIn("No AI provider was called", stdout.getvalue())
