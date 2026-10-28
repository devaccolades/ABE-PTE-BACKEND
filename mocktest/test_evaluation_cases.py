from collections import Counter
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from examinor.scoring.task_contracts import TASK_CONTRACTS
from examinor.services.rule_evaluator import run_rule_evaluation
from mocktest.evaluation_cases import CASES
from mocktest.evaluation_cases.answers import BUILDERS, build_key_answer
from mocktest.evaluation_cases.schema import (
    KeyAnswer, Observation, check_expectations, validate_case,
)
from mocktest.models import MockTest, MockTestSection, Question, QuestionOption, Section, SubSection


class EvaluationCaseDefinitionTests(SimpleTestCase):
    def test_case_ids_are_unique(self):
        duplicates = [case_id for case_id, count in Counter(c.id for c in CASES).items() if count > 1]
        self.assertEqual(duplicates, [])

    def test_every_case_is_well_formed(self):
        for case in CASES:
            with self.subTest(case=case.id):
                self.assertEqual(validate_case(case), [])

    def test_every_task_type_has_cases(self):
        self.assertEqual(set(TASK_CONTRACTS) - {case.task for case in CASES}, set())

    def test_key_answers_have_a_builder(self):
        for case in CASES:
            if isinstance(case.answer, KeyAnswer):
                with self.subTest(case=case.id):
                    self.assertIn(case.task, BUILDERS)

    def test_each_question_id_has_one_name_and_task(self):
        seen = {}
        for case in CASES:
            identity = (case.question_name, case.task)
            with self.subTest(case=case.id):
                self.assertEqual(seen.setdefault(case.question_id, identity), identity)


class ExpectationCheckTests(SimpleTestCase):
    def completed(self, **scores):
        return Observation(status="completed", scores=scores)

    def test_status_mismatch_reports_the_error(self):
        observation = Observation(status="failed", error="[source_fidelity_unavailable] uncertain")
        failures = check_expectations({"zero": True}, observation)
        self.assertEqual(len(failures), 1)
        self.assertIn("source_fidelity_unavailable", failures[0])

    def test_expected_failure_passes(self):
        self.assertEqual(check_expectations({"status": "failed"}, Observation(status="failed")), [])

    def test_zero_expectations(self):
        zero = self.completed(content=(0, 4), form=(0, 1))
        scored = self.completed(content=(2, 4), form=(1, 1))
        self.assertEqual(check_expectations({"zero": True}, zero), [])
        self.assertEqual(len(check_expectations({"zero": True}, scored)), 1)
        self.assertEqual(check_expectations({"zero": False}, scored), [])
        self.assertEqual(len(check_expectations({"zero": False}, zero)), 1)

    def test_zero_uses_the_gated_awarded_score(self):
        # Content 0 keeps delivery marks in the traits, but the gate awards nothing.
        gated = self.completed(content=(0, 3), pronunciation=(4, 5))
        gated.awarded = 0.0
        self.assertEqual(check_expectations({"zero": True}, gated), [])
        self.assertEqual(len(check_expectations({"zero": False}, gated)), 1)

    def test_override_expectations(self):
        observation = self.completed(content=(0, 4))
        observation.overrides = ("company_strict_form",)
        self.assertEqual(check_expectations({"override": "company_strict_form"}, observation), [])
        self.assertIn("source_fidelity_failed", check_expectations({"override": "source_fidelity_failed"}, observation)[0])
        self.assertEqual(len(check_expectations({"no_override": True}, observation)), 1)

    def test_ratio_bounds_tolerate_float_rounding(self):
        observation = self.completed(reading=(1 / 3, 1))
        self.assertEqual(check_expectations({"ratio": (1 / 3, 1 / 3)}, observation), [])
        self.assertEqual(len(check_expectations({"ratio": (0.5, 1)}, observation)), 1)

    def test_trait_bounds_and_missing_traits(self):
        observation = self.completed(content=(3, 4))
        self.assertEqual(check_expectations({"traits": {"content": (3, 4)}}, observation), [])
        self.assertEqual(len(check_expectations({"traits": {"content": (4, 4)}}, observation)), 1)
        self.assertIn("missing", check_expectations({"traits": {"form": (0, 1)}}, observation)[0])

    def test_validate_case_rejects_bad_definitions(self):
        case = CASES[0]
        bad = type(case)(**{**vars(case), "task": "nope", "expect": {"ratio": (1, 0), "colour": 1}})
        problems = validate_case(bad)
        self.assertEqual(len(problems), 3)


class KeyAnswerBuilderTests(TestCase):
    """Built answers use the frontend payload shapes and score as intended."""

    def question(self, task, options):
        section = Section.objects.create(name="Reading")
        subsection = SubSection.objects.create(
            section=section, name=task, evaluation_type="rule",
            rubric={"reading": {"max": 1}}, trait_skill_map={"reading": ["reading"]},
        )
        mock_test_section = MockTestSection.objects.create(
            mock_test=MockTest.objects.create(title=task), section=section,
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section, subsection=subsection, text="Question",
        )
        for text, is_correct, position in options:
            QuestionOption.objects.create(
                question=question, option_text=text, is_correct=is_correct, order_position=position,
            )
        return question

    def ratio(self, question, variant):
        answer = build_key_answer(question.subsection.name, question, variant)
        result = run_rule_evaluation(
            user_answer=SimpleNamespace(answer_data=answer), question=question, subsection=question.subsection,
        )
        self.assertTrue(result["ok"], result)
        return result["evaluation"]["scores"]["reading"]["score"]

    def test_reorder_answers(self):
        question = self.question("reorder_paragraphs", [(f"P{i}", False, i) for i in (1, 2, 3, 4)])
        self.assertEqual(build_key_answer("reorder_paragraphs", question, "correct"),
                         {str(i): option.id for i, option in enumerate(question.options.order_by("order_position"), 1)})
        self.assertEqual(self.ratio(question, "correct"), 1)
        self.assertEqual(self.ratio(question, "reversed"), 0)
        self.assertAlmostEqual(self.ratio(question, "swap_first_two"), 1 / 3)

    def test_drag_drop_answers(self):
        question = self.question("fib_drag_drop", [
            ("one", True, 1), ("two", True, 2), ("three", True, 3), ("spare", False, 4),
        ])
        self.assertEqual(self.ratio(question, "correct"), 1)
        self.assertEqual(self.ratio(question, "wrong"), 0)
        self.assertAlmostEqual(self.ratio(question, "first_correct"), 1 / 3)

    def test_multiple_choice_answers(self):
        question = self.question("mc_multiple", [("a", True, None), ("b", True, None), ("c", False, None)])
        self.assertEqual(self.ratio(question, "correct"), 1)
        self.assertEqual(self.ratio(question, "one_correct"), 0.5)
        self.assertEqual(self.ratio(question, "correct_plus_wrong"), 0.5)
        self.assertEqual(self.ratio(question, "wrong"), 0)

    def test_unknown_variant_names_the_choices(self):
        question = self.question("mc_single", [("a", True, None), ("b", False, None)])
        with self.assertRaisesMessage(ValueError, "choose from ['correct', 'wrong']"):
            build_key_answer("mc_single", question, "half")
