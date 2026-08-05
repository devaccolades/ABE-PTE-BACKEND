from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from examinor.scoring.task_contracts import (
    PayloadStatus,
    inspect_answer_payload,
)
from examinor.services.rule_evaluator import run_rule_evaluation
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


class DelimitedMultipleChoiceEvaluationTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Listening")
        self.subsection = SubSection.objects.create(
            section=section,
            name="l_mc_multiple",
            evaluation_type="rule",
            rubric={"listening": {"max": 1}},
            trait_skill_map={"listening": ["listening"]},
        )
        mock_test = MockTest.objects.create(title="Multiple choice repair")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
        )
        self.question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=self.subsection,
            text="Choose all correct answers.",
            listening_score_max=1,
        )
        self.correct_options = [
            QuestionOption.objects.create(
                question=self.question,
                option_text=f"Correct {index}",
                is_correct=True,
            )
            for index in range(1, 4)
        ]
        self.wrong_option = QuestionOption.objects.create(
            question=self.question,
            option_text="Wrong",
        )
        self.session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="multiple-choice-repair-session",
            mock_test=mock_test,
        )

    def _create_response(self, answer_data):
        return UserResponse.objects.create(
            user_session=self.session,
            mock_test=self.session.mock_test,
            question=self.question,
            answer_data=answer_data,
            evaluated=True,
            evaluation_status="completed",
            evaluation_result={
                "ok": True,
                "evaluation": {
                    "scores": {"listening": {"score": 0, "max": 1}},
                    "weighted_score": 0,
                    "max_score": 1,
                },
            },
        )

    def test_contract_classifies_comma_delimited_ids_as_legacy_compatible(self):
        answer = ",".join(str(option.id) for option in self.correct_options[:2])

        inspection = inspect_answer_payload("l_mc_multiple", answer)

        self.assertEqual(inspection.status, PayloadStatus.LEGACY_COMPATIBLE)
        self.assertEqual(
            inspection.normalized,
            [option.id for option in self.correct_options[:2]],
        )
        self.assertIn(
            "delimited_multiple_choice_answer",
            {issue.code for issue in inspection.issues},
        )

    def test_rule_evaluator_scores_comma_delimited_ids(self):
        answer = ",".join(str(option.id) for option in self.correct_options[:2])
        response = self._create_response(answer)

        result = run_rule_evaluation(
            user_answer=response,
            question=self.question,
            subsection=self.subsection,
        )

        self.assertTrue(result["ok"])
        self.assertAlmostEqual(
            result["evaluation"]["scores"]["listening"]["score"],
            0.67,
        )

    def test_repair_command_dry_run_does_not_change_response(self):
        answer = ",".join(str(option.id) for option in self.correct_options)
        response = self._create_response(answer)
        output = StringIO()

        call_command(
            "repair_delimited_multiple_choice_responses",
            stdout=output,
        )

        response.refresh_from_db()
        self.assertEqual(response.answer_data, answer)
        self.assertEqual(response.listening_score_awarded, 0)
        self.assertIn("Eligible responses: 1", output.getvalue())
        self.assertIn("Score-changing responses: 1", output.getvalue())
        self.assertIn("Dry run only", output.getvalue())

    def test_repair_command_requires_matching_expected_count(self):
        answer = ",".join(str(option.id) for option in self.correct_options)
        response = self._create_response(answer)

        with self.assertRaisesRegex(CommandError, "Eligible count changed"):
            call_command(
                "repair_delimited_multiple_choice_responses",
                "--confirm",
                "--expected-count",
                "2",
            )

        response.refresh_from_db()
        self.assertEqual(response.answer_data, answer)

    def test_repair_command_normalizes_scores_and_session_totals(self):
        answer = ",".join(str(option.id) for option in self.correct_options)
        response = self._create_response(answer)
        output = StringIO()

        call_command(
            "repair_delimited_multiple_choice_responses",
            "--confirm",
            "--expected-count",
            "1",
            stdout=output,
        )

        response.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(
            response.answer_data,
            [option.id for option in self.correct_options],
        )
        self.assertEqual(
            response.evaluation_result["evaluation"]["scores"]["listening"][
                "score"
            ],
            1.0,
        )
        self.assertEqual(response.listening_score_awarded, 1.0)
        self.assertEqual(self.session.listening_score_awarded, 1.0)
        self.assertIn("Repaired 1 response(s)", output.getvalue())

    def test_repair_command_rejects_option_ids_from_another_question(self):
        other_question = Question.objects.create(
            mock_test_section=self.question.mock_test_section,
            subsection=self.subsection,
            text="Another question",
            listening_score_max=1,
        )
        foreign_option = QuestionOption.objects.create(
            question=other_question,
            option_text="Foreign",
            is_correct=True,
        )
        answer = f"{self.correct_options[0].id},{foreign_option.id}"
        self._create_response(answer)

        with self.assertRaisesRegex(CommandError, "candidate validation failed"):
            call_command("repair_delimited_multiple_choice_responses")
