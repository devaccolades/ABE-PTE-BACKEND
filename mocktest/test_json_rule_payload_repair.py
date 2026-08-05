import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from examinor.services.rule_evaluator import run_rule_evaluation
from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    Section,
    SubQuestion,
    SubSection,
    UserMockTestSession,
    UserResponse,
)


class JsonEncodedRuleResponseRepairTests(TestCase):
    def setUp(self):
        self.section = Section.objects.create(name="Reading")
        self.mock_test = MockTest.objects.create(title="JSON rule repair")
        self.mock_test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=self.section,
        )
        self.session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="json-rule-repair-session",
            mock_test=self.mock_test,
        )
        self.responses = [
            self._dropdown_response(),
            self._multiple_choice_response(),
            self._reorder_response(),
            self._drag_drop_response(),
        ]

    def _subsection(self, name):
        return SubSection.objects.create(
            section=self.section,
            name=name,
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
            trait_skill_map={"reading": ["reading"]},
        )

    def _question(self, subsection, text):
        return Question.objects.create(
            mock_test_section=self.mock_test_section,
            subsection=subsection,
            text=text,
            reading_score_max=1,
        )

    def _response(self, question, answer_data):
        return UserResponse.objects.create(
            user_session=self.session,
            mock_test=self.mock_test,
            question=question,
            answer_data=answer_data,
            evaluated=True,
            evaluation_status="completed",
            evaluation_result={
                "ok": True,
                "evaluation": {
                    "scores": {"reading": {"score": 0, "max": 1}},
                    "weighted_score": 0,
                    "max_score": 1,
                },
            },
        )

    def _dropdown_response(self):
        question = self._question(
            self._subsection("fib_dropdown"),
            "One ____ two ____.",
        )
        answer = {}
        for blank_number in (1, 2):
            subquestion = SubQuestion.objects.create(
                question=question,
                blank_number=blank_number,
            )
            correct = QuestionOption.objects.create(
                sub_question=subquestion,
                option_text=f"Correct {blank_number}",
                is_correct=True,
            )
            answer[str(blank_number)] = str(correct.id)
        return self._response(question, json.dumps(answer))

    def _multiple_choice_response(self):
        question = self._question(
            self._subsection("mc_multiple"),
            "Choose all correct answers.",
        )
        correct = [
            QuestionOption.objects.create(
                question=question,
                option_text=f"Correct {index}",
                is_correct=True,
            )
            for index in (1, 2)
        ]
        return self._response(
            question,
            json.dumps([option.id for option in correct]),
        )

    def _reorder_response(self):
        question = self._question(
            self._subsection("reorder_paragraphs"),
            "Order the paragraphs.",
        )
        options = [
            QuestionOption.objects.create(
                question=question,
                option_text=f"Paragraph {position}",
                order_position=position,
            )
            for position in (1, 2, 3)
        ]
        answer = {
            str(position): option.id
            for position, option in enumerate(options, start=1)
        }
        return self._response(question, json.dumps(answer))

    def _drag_drop_response(self):
        question = self._question(
            self._subsection("fib_drag_drop"),
            "One ____ two ____.",
        )
        options = [
            QuestionOption.objects.create(
                question=question,
                option_text=f"Correct {position}",
                order_position=position,
                is_correct=True,
            )
            for position in (1, 2)
        ]
        answer = {
            str(position): option.id
            for position, option in enumerate(options, start=1)
        }
        return self._response(question, json.dumps(answer))

    def test_rule_evaluator_scores_json_encoded_legacy_answers(self):
        for response in self.responses:
            with self.subTest(subsection=response.question.subsection.name):
                result = run_rule_evaluation(
                    user_answer=response,
                    question=response.question,
                    subsection=response.question.subsection,
                )
                self.assertTrue(result["ok"])
                self.assertEqual(
                    result["evaluation"]["scores"]["reading"]["score"],
                    1.0,
                )

    def test_dry_run_reports_candidates_without_writes(self):
        output = StringIO()

        call_command("repair_json_encoded_rule_responses", stdout=output)

        for response in self.responses:
            response.refresh_from_db()
            self.assertIsInstance(response.answer_data, str)
            self.assertEqual(response.reading_score_awarded, 0)
        self.assertIn("Eligible responses: 4", output.getvalue())
        self.assertIn("Score-changing responses: 4", output.getvalue())
        self.assertIn("Dry run only", output.getvalue())

    def test_confirm_requires_matching_expected_count(self):
        with self.assertRaisesRegex(CommandError, "Eligible count changed"):
            call_command(
                "repair_json_encoded_rule_responses",
                "--confirm",
                "--expected-count",
                "5",
            )

        for response in self.responses:
            response.refresh_from_db()
            self.assertIsInstance(response.answer_data, str)

    def test_confirm_normalizes_answers_scores_and_session(self):
        output = StringIO()

        call_command(
            "repair_json_encoded_rule_responses",
            "--confirm",
            "--expected-count",
            "4",
            stdout=output,
        )

        for response in self.responses:
            response.refresh_from_db()
            self.assertNotIsInstance(response.answer_data, str)
            self.assertEqual(response.reading_score_awarded, 1.0)
        self.session.refresh_from_db()
        self.assertEqual(self.session.reading_score_awarded, 4.0)
        self.assertIn("Repaired 4 response(s)", output.getvalue())

    def test_foreign_dropdown_option_blocks_entire_repair(self):
        other_question = self._question(
            self.responses[0].question.subsection,
            "Another ____ question.",
        )
        other_blank = SubQuestion.objects.create(
            question=other_question,
            blank_number=1,
        )
        foreign_option = QuestionOption.objects.create(
            sub_question=other_blank,
            option_text="Foreign",
            is_correct=True,
        )
        response = self.responses[0]
        response.answer_data = json.dumps({"1": str(foreign_option.id)})
        response.save(update_fields=["answer_data"])

        with self.assertRaisesRegex(CommandError, "candidate validation failed"):
            call_command("repair_json_encoded_rule_responses")

        for stored_response in self.responses:
            stored_response.refresh_from_db()
            self.assertIsInstance(stored_response.answer_data, str)
