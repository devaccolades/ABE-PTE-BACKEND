import json

from django.test import SimpleTestCase

from examinor.scoring.contracts import SCORING_VERSION, ScoringContractError
from examinor.scoring.score_calculator import compile_skill_scores


class GoldenScoreCompilerTests(SimpleTestCase):
    def test_approved_golden_examples(self):
        examples = [
            {
                "name": "reading_fib_full",
                "criteria": {"reading": {"score": 4, "max": 4}},
                "mapping": {"reading": ["reading"]},
                "maxima": {"reading": 4},
                "expected": {"reading": 4},
            },
            {
                "name": "reading_fib_partial",
                "criteria": {"reading": {"score": 1, "max": 4}},
                "mapping": {"reading": ["reading"]},
                "maxima": {"reading": 4},
                "expected": {"reading": 1},
            },
            {
                "name": "reorder_paragraphs_full",
                "criteria": {"reading": {"score": 3, "max": 3}},
                "mapping": {"reading": ["reading"]},
                "maxima": {"reading": 3},
                "expected": {"reading": 3},
            },
            {
                "name": "drag_drop_partial",
                "criteria": {"reading": {"score": 4, "max": 5}},
                "mapping": {"reading": ["reading"]},
                "maxima": {"reading": 5},
                "expected": {"reading": 4},
            },
            {
                "name": "listening_fib_full",
                "criteria": {"listening": {"score": 4, "max": 4}},
                "mapping": {"listening": ["listening"]},
                "maxima": {"listening": 4},
                "expected": {"listening": 4},
            },
            {
                "name": "highlight_incorrect_words_full",
                "criteria": {"listening_and_reading": {"score": 1, "max": 1}},
                "mapping": {
                    "listening_and_reading": ["reading", "listening"],
                },
                "maxima": {"reading": 5.5, "listening": 4},
                "expected": {"reading": 5.5, "listening": 4},
            },
            {
                "name": "write_from_dictation_full",
                "criteria": {"listening_and_writing": {"score": 7, "max": 7}},
                "mapping": {
                    "listening_and_writing": ["writing", "listening"],
                },
                "maxima": {"writing": 7, "listening": 1},
                "expected": {"writing": 7, "listening": 1},
            },
            {
                "name": "repeat_sentence_content_partial",
                "criteria": {"content": {"score": 2, "max": 3}},
                "mapping": {"content": ["listening"]},
                "maxima": {"listening": 1.5},
                "expected": {"listening": 1},
            },
            {
                "name": "repeat_sentence_speech_partial",
                "criteria": {
                    "oral_fluency": {"score": 4, "max": 5},
                    "pronunciation": {"score": 5, "max": 5},
                },
                "mapping": {
                    "oral_fluency": ["speaking"],
                    "pronunciation": ["speaking"],
                },
                "maxima": {"speaking": 1.4},
                "expected": {"speaking": 1.26},
            },
        ]

        for example in examples:
            with self.subTest(example["name"]):
                result = compile_skill_scores(
                    example["criteria"],
                    example["mapping"],
                    example["maxima"],
                )

                self.assertEqual(result["scoring_version"], SCORING_VERSION)
                for skill, expected in example["expected"].items():
                    self.assertAlmostEqual(
                        result["skills"][skill]["score"],
                        expected,
                    )

    def test_scales_criterion_ratio_to_configured_question_maximum(self):
        result = compile_skill_scores(
            {
                "content": {"score": 2, "max": 3},
                "grammar": {"score": 1, "max": 2},
            },
            {
                "content": ["writing"],
                "grammar": ["writing"],
            },
            {"writing": 4},
        )

        self.assertAlmostEqual(result["skills"]["writing"]["score"], 2.4)
        self.assertAlmostEqual(result["skills"]["writing"]["ratio"], 0.6)

    def test_one_criterion_contributes_independently_to_multiple_skills(self):
        result = compile_skill_scores(
            {"content": {"score": 3, "max": 6}},
            {"content": ["speaking", "reading"]},
            {"speaking": 2, "reading": 6},
        )

        self.assertAlmostEqual(result["skills"]["speaking"]["score"], 1)
        self.assertAlmostEqual(result["skills"]["reading"]["score"], 3)

    def test_gate_is_applied_only_when_explicitly_supplied(self):
        arguments = (
            {
                "content": {"score": 0, "max": 3},
                "grammar": {"score": 2, "max": 2},
            },
            {
                "content": ["writing"],
                "grammar": ["writing"],
            },
            {"writing": 10},
        )

        ungated = compile_skill_scores(*arguments)
        gated = compile_skill_scores(*arguments, gate_traits=("content",))

        self.assertAlmostEqual(ungated["skills"]["writing"]["score"], 4)
        self.assertEqual(gated["skills"]["writing"]["score"], 0)
        self.assertEqual(gated["gate"]["triggered_by"], ["content"])

    def test_rejects_invalid_criterion_numbers(self):
        invalid_cases = [
            ({"score": "nan", "max": 1}, "finite"),
            ({"score": "inf", "max": 1}, "finite"),
            ({"score": -1, "max": 1}, "negative"),
            ({"score": 2, "max": 1}, "exceeds"),
            ({"score": 0, "max": 0}, "greater than zero"),
        ]

        for payload, message in invalid_cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ScoringContractError, message):
                    compile_skill_scores(
                        {"content": payload},
                        {"content": ["writing"]},
                        {"writing": 1},
                    )

    def test_rejects_missing_mapping_and_question_maximum(self):
        with self.assertRaisesRegex(ScoringContractError, "no skill mapping"):
            compile_skill_scores(
                {"content": {"score": 1, "max": 1}},
                {},
                {"writing": 1},
            )

        with self.assertRaisesRegex(ScoringContractError, "Missing positive"):
            compile_skill_scores(
                {"content": {"score": 1, "max": 1}},
                {"content": ["writing"]},
                {},
            )

    def test_rejects_duplicate_normalized_criterion_names(self):
        with self.assertRaisesRegex(ScoringContractError, "Duplicate normalized"):
            compile_skill_scores(
                {
                    "content": {"score": 1, "max": 1},
                    " content ": {"score": 1, "max": 1},
                },
                {"content": ["writing"]},
                {"writing": 1},
            )

    def test_repeated_compilation_is_deterministic(self):
        arguments = (
            {
                "grammar": {"score": 1, "max": 2},
                "content": {"score": 2, "max": 3},
            },
            {
                "grammar": ["writing"],
                "content": ["writing"],
            },
            {"writing": 4},
        )

        first = compile_skill_scores(*arguments)
        second = compile_skill_scores(*arguments)

        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )
