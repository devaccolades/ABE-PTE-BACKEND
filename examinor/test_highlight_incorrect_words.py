from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from examinor.scoring.task_contracts import PayloadStatus, inspect_answer_payload
from examinor.services.highlight_incorrect_words import (
    HighlightIncorrectWordsError,
    assess_highlighted_words,
    compare_displayed_text_to_source,
)
from examinor.services.rule_evaluator import run_rule_evaluation
from mocktest.models import Question, Section, SubSection


DISPLAYED = "The cat sat on the blue mat."
SOURCE = "The dog sat on the red mat."


class HighlightIncorrectWordComparisonTests(SimpleTestCase):
    def test_derives_incorrect_displayed_words_and_positions(self):
        comparison = compare_displayed_text_to_source(DISPLAYED, SOURCE)

        self.assertEqual(
            [(item.word_index, item.word, item.expected) for item in comparison.incorrect_words],
            [(1, "cat", "dog"), (5, "blue", "red")],
        )
        self.assertGreater(comparison.alignment_ratio, 0.7)

    def test_requires_source_transcript(self):
        with self.assertRaisesRegex(
            HighlightIncorrectWordsError,
            "source-audio transcript",
        ):
            compare_displayed_text_to_source(DISPLAYED, "")

    def test_reports_source_insertions_as_unscorable(self):
        comparison = compare_displayed_text_to_source(
            "The cat sat.",
            "The small dog sat.",
        )

        self.assertFalse(comparison.as_dict()["scorable"])
        self.assertEqual(comparison.source_only_words, ("dog",))
        with self.assertRaisesRegex(
            HighlightIncorrectWordsError,
            "cannot be selected by the candidate",
        ):
            assess_highlighted_words(
                "The cat sat.",
                "The small dog sat.",
                {"mode": "positions", "selections": []},
            )

    def test_scores_displayed_words_that_are_absent_from_audio(self):
        comparison = compare_displayed_text_to_source(
            "The very blue mat.",
            "The blue mat.",
        )

        self.assertTrue(comparison.as_dict()["scorable"])
        self.assertEqual(
            [item.word for item in comparison.incorrect_words if not item.expected],
            ["very"],
        )
        assessment = assess_highlighted_words(
            "The very blue mat.",
            "The blue mat.",
            {
                "mode": "positions",
                "selections": [{"word_index": 1, "word": "very"}],
            },
        )
        self.assertEqual(assessment["ratio"], 1)

    def test_scores_positioned_selections_with_wrong_selection_penalty(self):
        assessment = assess_highlighted_words(
            DISPLAYED,
            SOURCE,
            {
                "mode": "positions",
                "selections": [
                    {"word_index": 1, "word": "cat"},
                    {"word_index": 2, "word": "sat"},
                ],
            },
        )

        self.assertEqual(assessment["awarded"], 0)
        self.assertEqual(assessment["ratio"], 0)
        self.assertEqual(len(assessment["correct_selected"]), 1)
        self.assertEqual(len(assessment["incorrect_selected"]), 1)
        self.assertEqual(len(assessment["missed"]), 1)

    def test_legacy_word_list_remains_compatible(self):
        inspection = inspect_answer_payload(
            "highlight_incorrect_words",
            "cat,blue",
        )

        self.assertEqual(inspection.status, PayloadStatus.LEGACY_COMPATIBLE)
        assessment = assess_highlighted_words(
            DISPLAYED,
            SOURCE,
            inspection.normalized,
        )
        self.assertEqual(assessment["ratio"], 1)

    def test_positioned_payload_is_canonical(self):
        inspection = inspect_answer_payload(
            "highlight_incorrect_words",
            {
                "selections": [
                    {"word_index": 1, "word": "cat"},
                    {"word_index": 5, "word": "blue"},
                ]
            },
        )

        self.assertEqual(inspection.status, PayloadStatus.CANONICAL)
        self.assertEqual(inspection.normalized["mode"], "positions")


class HighlightIncorrectWordRuleEvaluationTests(TestCase):
    def test_rule_evaluator_scores_from_source_transcript_without_openai(self):
        section = Section.objects.create(name="Listening")
        subsection = SubSection.objects.create(
            section=section,
            name="highlight_incorrect_words",
            evaluation_type="ai",
            rubric={"listening_and_reading": {"max": 4}},
        )
        question = Question.objects.create(
            subsection=subsection,
            text=DISPLAYED,
            correct_answer=SOURCE,
        )
        response = SimpleNamespace(
            answer_data={
                "selections": [
                    {"word_index": 1, "word": "cat"},
                    {"word_index": 5, "word": "blue"},
                ]
            }
        )

        result = run_rule_evaluation(
            user_answer=response,
            question=question,
            subsection=subsection,
        )

        self.assertTrue(result["ok"])
        score = result["evaluation"]["scores"]["listening_and_reading"]
        self.assertEqual(score, {"score": 4.0, "max": 4.0})
        self.assertIn(
            "Highlighted 2 correct word(s)",
            result["evaluation"]["feedback"]["summary"],
        )
