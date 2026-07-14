from unittest.mock import patch
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.test import override_settings

from examinor.scoring.validators import validate_and_normalize_evaluation_result
from examinor.models import EvaluationCache
from examinor.services.evaluator import evaluate_with_openai
from examinor.services.orchestrator import (
    run_evaluation,
    run_evaluation_for_subsection,
    save_evaluation_cache,
)
from examinor.services.prompt_builder import build_prompt, normalize_answer_text
from examinor.services.rule_evaluator import run_rule_evaluation, uses_rule_evaluation
from examinor.services.explanation_drafter import draft_question_explanation
from mocktest.services.transcription import transcribe_audio
from mocktest.models import Question, QuestionOption, Section, SubQuestion, SubSection


class EvaluationResultValidatorTests(SimpleTestCase):
    def test_accepts_and_normalizes_valid_scores(self):
        result = {
            "ok": True,
            "evaluation": {
                "scores": {
                    "content": {"score": "2", "max": "3"},
                    "form": {"score": 1, "max": 2},
                }
            },
        }
        rubric = {
            "content": {"max": 3},
            "form": {"max": 2},
        }

        is_valid, normalized, error = validate_and_normalize_evaluation_result(result, rubric)

        self.assertTrue(is_valid)
        self.assertIsNone(error)
        self.assertEqual(normalized["evaluation"]["scores"]["content"]["score"], 2.0)
        self.assertEqual(normalized["evaluation"]["scores"]["content"]["max"], 3.0)
        self.assertEqual(normalized["evaluation"]["weighted_score"], 3.0)
        self.assertEqual(normalized["evaluation"]["max_score"], 5.0)

    def test_rejects_missing_rubric_key(self):
        result = {
            "ok": True,
            "evaluation": {
                "scores": {
                    "content": {"score": 2, "max": 3},
                }
            },
        }
        rubric = {
            "content": {"max": 3},
            "form": {"max": 2},
        }

        is_valid, normalized, error = validate_and_normalize_evaluation_result(result, rubric)

        self.assertFalse(is_valid)
        self.assertIsNone(normalized)
        self.assertIn("missing rubric score keys", error)

    def test_rejects_score_above_max(self):
        result = {
            "ok": True,
            "evaluation": {
                "scores": {
                    "content": {"score": 4, "max": 3},
                }
            },
        }
        rubric = {
            "content": {"max": 3},
        }

        is_valid, normalized, error = validate_and_normalize_evaluation_result(result, rubric)

        self.assertFalse(is_valid)
        self.assertIsNone(normalized)
        self.assertIn("exceeds max", error)


class OpenAIServiceConfigurationTests(SimpleTestCase):
    @override_settings(OPENAI_API_KEY="")
    def test_evaluator_returns_structured_error_when_key_missing(self):
        result = evaluate_with_openai("prompt", "hash-1")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "OPENAI_API_KEY is missing")
        self.assertEqual(result["prompt_hash"], "hash-1")

    @override_settings(OPENAI_WHISPER_API_KEY="")
    def test_transcription_raises_clear_error_when_key_missing(self):
        with self.assertRaisesRegex(RuntimeError, "OPENAI_WHISPER_API_KEY is missing"):
            transcribe_audio("/tmp/nonexistent-audio.wav")


class EvaluationOrchestratorTests(TestCase):
    def test_name_based_evaluation_rejects_duplicate_subsections(self):
        section = Section.objects.create(name="Writing")
        SubSection.objects.create(
            section=section,
            name="write_essay",
            rubric={"content": {"max": 3}},
        )
        SubSection.objects.create(
            section=section,
            name="write_essay",
            rubric={"content": {"max": 5}},
        )

        result = run_evaluation(
            "write_essay",
            "Question text",
            {"answer_data": "Answer text"},
        )

        self.assertFalse(result["ok"])
        self.assertIn("Duplicate subsection name", result["error"])

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_summarize_spoken_text_requires_reference_material(self, mock_evaluate):
        section = Section.objects.create(name="Listening")
        subsection = SubSection.objects.create(
            section=section,
            name="summarize_spoken_text",
            rubric={"content": {"max": 4}},
        )

        result = run_evaluation_for_subsection(
            subsection,
            "SST-1",
            {"answer_data": "Candidate summary"},
        )

        self.assertFalse(result["ok"])
        self.assertIn("requires a reference transcript", result["error"])
        mock_evaluate.assert_not_called()

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_object_based_evaluation_uses_linked_subsection_rubric(self, mock_evaluate):
        section = Section.objects.create(name="Writing")
        SubSection.objects.create(
            section=section,
            name="write_essay",
            rubric={"content": {"max": 3}},
        )
        linked_subsection = SubSection.objects.create(
            section=section,
            name="write_essay",
            rubric={"content": {"max": 5}},
        )
        mock_evaluate.return_value = {
            "success": True,
            "data": {
                "scores": {"content": {"score": 4, "max": 5}},
                "weighted_score": 4,
                "max_score": 5,
            },
        }

        result = run_evaluation_for_subsection(
            linked_subsection,
            "Question text",
            {"answer_data": "Answer text"},
        )

        self.assertTrue(result["ok"])
        prompt = mock_evaluate.call_args.args[0]
        self.assertIn('"content":{"max":5}', prompt)

    @override_settings(OPENAI_EVALUATION_MODEL="new-model")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_cache_is_scoped_by_evaluation_model(self, mock_evaluate):
        section = Section.objects.create(name="Writing")
        subsection = SubSection.objects.create(
            section=section,
            name="write_essay",
            rubric={"content": {"max": 5}},
        )
        prompt, prompt_hash = build_prompt(
            "write_essay",
            "Question text",
            {"answer_data": "Answer text"},
            {"content": {"max": 5}},
        )
        EvaluationCache.objects.create(
            prompt_hash=prompt_hash,
            model="old-model",
            result={
                "scores": {"content": {"score": 1, "max": 5}},
                "weighted_score": 1,
                "max_score": 5,
            },
        )
        mock_evaluate.return_value = {
            "success": True,
            "data": {
                "scores": {"content": {"score": 4, "max": 5}},
                "weighted_score": 4,
                "max_score": 5,
            },
        }

        result = run_evaluation_for_subsection(
            subsection,
            "Question text",
            {"answer_data": "Answer text"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "new-model")
        self.assertFalse(result.get("cached", False))
        self.assertEqual(result["evaluation"]["weighted_score"], 4)
        self.assertEqual(mock_evaluate.call_args.args[0], prompt)
        self.assertTrue(
            EvaluationCache.objects.filter(
                prompt_hash=prompt_hash,
                model="new-model",
            ).exists()
        )

    def test_cache_write_race_reuses_existing_result(self):
        EvaluationCache.objects.create(
            prompt_hash="hash-1",
            model="model-1",
            result={"weighted_score": 2},
        )
        from django.db import IntegrityError

        with patch(
            "examinor.services.orchestrator.EvaluationCache.objects.create",
            side_effect=IntegrityError("duplicate"),
        ):
            result = save_evaluation_cache(
                "hash-1",
                "model-1",
                {"weighted_score": 5},
            )

        self.assertEqual(result, {"weighted_score": 2})


class PromptBuilderTests(SimpleTestCase):
    def test_normalizes_common_text_answer_payloads(self):
        self.assertEqual(
            normalize_answer_text({"text": "Candidate answer"}),
            "Candidate answer",
        )
        self.assertEqual(
            normalize_answer_text({"answer": {"text": "Nested answer"}}),
            "Nested answer",
        )
        self.assertEqual(
            normalize_answer_text(["one", {"text": "two"}]),
            "one\ntwo",
        )

    def test_prompt_uses_candidate_text_not_raw_python_dict(self):
        prompt, _ = build_prompt(
            "write_essay",
            "Question text",
            {"answer_data": {"text": "Candidate answer"}},
            {"content": {"max": 3}},
        )

        self.assertIn('"""Candidate answer"""', prompt)
        self.assertNotIn("{'text': 'Candidate answer'}", prompt)

    def test_writing_prompt_requests_exact_spelling_and_grammar_errors(self):
        prompt, _ = build_prompt(
            "write_essay",
            "Question text",
            {"answer_data": "This are a bad sentnce."},
            {"grammar": {"max": 2}, "spelling": {"max": 2}},
        )

        self.assertIn('"errors":[{', prompt)
        self.assertIn('"type":"<spelling or grammar>"', prompt)
        self.assertIn("exact, case-preserving substring", prompt)
        self.assertIn("Do not include style preferences as grammar errors", prompt)

    def test_structured_answer_fallback_is_stable_json(self):
        first = normalize_answer_text({"b": 2, "a": 1})
        second = normalize_answer_text({"a": 1, "b": 2})

        self.assertEqual(first, second)
        self.assertEqual(first, '{"a": 1, "b": 2}')

    def test_summarize_spoken_text_prompt_is_grounded_and_requests_specific_feedback(self):
        prompt, _ = build_prompt(
            "summarize_spoken_text",
            "SST-1",
            {
                "answer_data": "Candidate summary",
                "reference_answer": "The lecture explains cultural exchange.",
            },
            {"content": {"max": 4}},
        )

        self.assertIn('"""The lecture explains cultural exchange."""', prompt)
        self.assertIn('"strengths"', prompt)
        self.assertIn('"improvements"', prompt)
        self.assertIn("Judge content only against REFERENCE_MATERIAL", prompt)


class RuleEvaluatorTests(TestCase):
    def setUp(self):
        self.section = Section.objects.create(name="Reading")

    def test_scores_single_choice_without_openai(self):
        subsection = SubSection.objects.create(
            section=self.section,
            name="mc_single",
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
        )
        question = Question.objects.create(subsection=subsection, text="Choose one.")
        wrong = QuestionOption.objects.create(question=question, option_text="Wrong")
        correct = QuestionOption.objects.create(
            question=question,
            option_text="Correct",
            is_correct=True,
        )

        class Answer:
            answer_data = {"selected_option_id": correct.id}

        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["evaluation"]["scores"]["reading"]["score"], 1.0)

        Answer.answer_data = {"selected_option_id": wrong.id}
        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertEqual(result["evaluation"]["scores"]["reading"]["score"], 0.0)

    def test_scores_fib_dropdown_by_blank_mapping(self):
        subsection = SubSection.objects.create(
            section=self.section,
            name="fib_dropdown",
            evaluation_type="rule",
            rubric={"reading": {"max": 2}},
        )
        question = Question.objects.create(subsection=subsection, text="Fill blanks.")
        blank_one = SubQuestion.objects.create(question=question, blank_number=1)
        blank_two = SubQuestion.objects.create(question=question, blank_number=2)
        correct_one = QuestionOption.objects.create(
            sub_question=blank_one,
            option_text="alpha",
            is_correct=True,
        )
        wrong_two = QuestionOption.objects.create(
            sub_question=blank_two,
            option_text="wrong",
        )
        correct_two = QuestionOption.objects.create(
            sub_question=blank_two,
            option_text="beta",
            is_correct=True,
        )

        class Answer:
            answer_data = {
                "1": correct_one.id,
                "2": wrong_two.id,
            }

        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["evaluation"]["scores"]["reading"]["score"], 1.0)
        self.assertEqual(result["evaluation"]["scores"]["reading"]["max"], 2.0)

        Answer.answer_data = {
            "1": correct_one.id,
            "2": correct_two.id,
        }
        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertEqual(result["evaluation"]["scores"]["reading"]["score"], 2.0)

    def test_scores_drag_drop_by_correct_blanks_not_option_pool_size(self):
        subsection = SubSection.objects.create(
            section=self.section,
            name="fib_drag_drop",
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
        )
        question = Question.objects.create(subsection=subsection, text="A ____ B ____ C ____ D ____")
        correct_options = [
            QuestionOption.objects.create(
                question=question,
                option_text=f"correct-{position}",
                is_correct=True,
                order_position=position,
            )
            for position in range(1, 5)
        ]
        distractors = [
            QuestionOption.objects.create(
                question=question,
                option_text=f"distractor-{position}",
                order_position=position,
            )
            for position in range(5, 10)
        ]

        class Answer:
            answer_data = {
                "1": correct_options[0].id,
                "2": distractors[0].id,
                "3": distractors[1].id,
                "4": distractors[2].id,
            }

        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertEqual(result["evaluation"]["scores"]["reading"]["score"], 0.25)
        feedback = result["evaluation"]["feedback"]
        self.assertEqual(feedback["summary"], "1 of 4 blanks were correct.")
        self.assertEqual(len(feedback["details"]), 4)
        self.assertEqual(feedback["details"][0]["status"], "correct")
        self.assertEqual(feedback["details"][1]["status"], "incorrect")

    def test_scores_reorder_paragraphs_by_adjacent_pairs(self):
        subsection = SubSection.objects.create(
            section=self.section,
            name="reorder_paragraphs",
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
        )
        question = Question.objects.create(subsection=subsection, text="Reorder these paragraphs.")
        options = [
            QuestionOption.objects.create(
                question=question,
                option_text=f"paragraph-{position}",
                order_position=position,
            )
            for position in range(1, 6)
        ]

        class Answer:
            answer_data = {
                "1": options[0].id,
                "2": options[1].id,
                "3": options[3].id,
                "4": options[2].id,
                "5": options[4].id,
            }

        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertEqual(result["evaluation"]["scores"]["reading"]["score"], 0.25)
        self.assertEqual(
            result["evaluation"]["feedback"]["summary"],
            "1 of 4 adjacent paragraph pair(s) were correct.",
        )

        Answer.answer_data = {
            str(position): option.id
            for position, option in enumerate(options, start=1)
        }
        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertEqual(result["evaluation"]["scores"]["reading"]["score"], 1.0)

    def test_scores_listening_blanks_per_position_from_pipe_delimited_answer(self):
        subsection = SubSection.objects.create(
            section=self.section,
            name="l_fill_in_blanks",
            evaluation_type="ai",
            rubric={"listening_and_writing": {"max": 4}},
        )
        question = Question.objects.create(subsection=subsection, text="A ____ B ____ C ____ D ____")
        for position, answer in enumerate(("alpha", "beta", "gamma", "delta"), start=1):
            SubQuestion.objects.create(
                question=question,
                blank_number=position,
                correct_answer=answer,
            )

        class Answer:
            answer_data = "alpha|wrong|gamma|delta"

        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertTrue(uses_rule_evaluation(subsection))
        self.assertEqual(
            result["evaluation"]["scores"]["listening_and_writing"]["score"],
            3.0,
        )
        self.assertEqual(
            result["evaluation"]["feedback"]["summary"],
            "3 of 4 answer(s) were correct.",
        )

    def test_scores_write_from_dictation_by_correct_words_in_sequence(self):
        subsection = SubSection.objects.create(
            section=self.section,
            name="write_from_dictation",
            evaluation_type="ai",
            rubric={"listening_and_writing": {"max": 10}},
        )
        question = Question.objects.create(
            subsection=subsection,
            correct_answer="The author expressed an idea which modern readers cannot accept",
        )

        class Answer:
            answer_data = "The author expressed an idea which modern readers cant accept."

        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertEqual(
            result["evaluation"]["scores"]["listening_and_writing"]["score"],
            9.0,
        )
        self.assertEqual(
            result["evaluation"]["feedback"]["summary"],
            "9 of 10 words were correct and in sequence.",
        )

    def test_highlight_incorrect_words_applies_wrong_selection_penalty(self):
        subsection = SubSection.objects.create(
            section=self.section,
            name="highlight_incorrect_words",
            evaluation_type="rule",
            rubric={"listening_and_reading": {"max": 3}},
        )
        question = Question.objects.create(
            subsection=subsection,
            text="Displayed transcript",
            correct_answer="ordinary|confusion|upset",
        )

        class Answer:
            answer_data = "ordinary,confusion,science"

        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertEqual(
            result["evaluation"]["scores"]["listening_and_reading"]["score"],
            1.0,
        )
        self.assertIn(
            "2 correct word(s), 1 incorrect word(s)",
            result["evaluation"]["feedback"]["summary"],
        )

    def test_highlight_incorrect_words_can_compare_reference_transcript(self):
        subsection = SubSection.objects.create(
            section=self.section,
            name="highlight_incorrect_words",
            evaluation_type="rule",
            rubric={"listening_and_reading": {"max": 1}},
        )
        question = Question.objects.create(
            subsection=subsection,
            text="Science can continue to upset us in surprising ways today.",
            correct_answer="Science can continue to surprise us in surprising ways today.",
        )

        class Answer:
            answer_data = "upset"

        result = run_rule_evaluation(
            user_answer=Answer(),
            question=question,
            subsection=subsection,
        )

        self.assertEqual(
            result["evaluation"]["scores"]["listening_and_reading"]["score"],
            1.0,
        )


class ExplanationDrafterTests(TestCase):
    @patch("examinor.services.explanation_drafter.get_openai_client")
    def test_drafts_reusable_explanation_from_correct_answer_data(self, get_client):
        section = Section.objects.create(name="Reading")
        subsection = SubSection.objects.create(section=section, name="mc_single")
        question = Question.objects.create(
            subsection=subsection,
            text="Which option is correct?",
        )
        QuestionOption.objects.create(
            question=question,
            option_text="Correct option",
            is_correct=True,
        )
        create = get_client.return_value.responses.create
        create.return_value = SimpleNamespace(
            output_text="The correct option follows directly from the passage."
        )

        explanation = draft_question_explanation(question)

        self.assertEqual(
            explanation,
            "The correct option follows directly from the passage.",
        )
        prompt = create.call_args.kwargs["input"]
        self.assertIn("Correct option", prompt)
        self.assertIn("Which option is correct?", prompt)
