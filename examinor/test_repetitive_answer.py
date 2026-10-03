from unittest import TestCase

from examinor.scoring.task_contracts import get_task_contract
from examinor.services.repetitive_answer import (
    OVERRIDE_CODE,
    apply_repetition_score_override,
    detect_repetitive_answer,
)


class RepetitiveAnswerDetectorTests(TestCase):
    def test_normal_descriptive_answer_passes(self):
        text = (
            "The photograph shows a busy public library during the afternoon. "
            "Several students are reading near large windows while a librarian "
            "organizes books behind the main desk. Sunlight makes the room feel "
            "welcoming, and the quiet setting suggests that everyone is focused "
            "on study or research."
        )

        result = detect_repetitive_answer(text, "describe_image")

        self.assertFalse(result["is_repetitive"])
        self.assertEqual(result["status"], "pass")

    def test_phrase_repeated_twice_naturally_does_not_trigger(self):
        text = (
            "Public transport can reduce traffic in growing cities. For this "
            "reason, local authorities should improve bus reliability and make "
            "stations safer. Better services also help workers arrive on time. "
            "For this reason, thoughtful investment benefits both commuters and "
            "the wider economy without artificially extending the discussion."
        )

        result = detect_repetitive_answer(text, "summarize_written_text")

        self.assertFalse(result["is_repetitive"])

    def test_same_phrase_repeated_several_times_triggers(self):
        text = " ".join(
            [
                "We observe a person standing beside a table with a notebook.",
                "We observe a person standing beside a table with a notebook.",
                "We observe a person standing beside a table with a notebook.",
                "We observe a person standing beside a table with a notebook.",
            ]
        )

        result = detect_repetitive_answer(text, "describe_image")

        self.assertTrue(result["is_repetitive"])
        self.assertEqual(result["status"], "hard_zero")
        self.assertGreaterEqual(result["repeated_phrases"][0]["count"], 3)

    def test_dominant_three_word_template_with_substitutions_triggers(self):
        text = " ".join(
            [
                "There is a teacher beside the entrance.",
                "There is a student beside the window.",
                "There is a bicycle beside the building.",
                "There is a table beside the doorway.",
                "There is a poster beside the staircase.",
                "There is a computer beside the cabinet.",
            ]
        )

        result = detect_repetitive_answer(text, "describe_image")

        self.assertTrue(result["is_repetitive"])
        self.assertIn(
            "there is a",
            [item["phrase"] for item in result["repeated_phrases"]],
        )

    def test_repeated_sentence_openings_are_detected(self):
        text = " ".join(
            [
                "At the front of the image a child is holding a yellow ball.",
                "At the front of the image a teacher is opening a blue folder.",
                "At the front of the image a parent is carrying a green bag.",
                "At the front of the image a student is moving a wooden chair.",
            ]
        )

        result = detect_repetitive_answer(text, "describe_image")

        self.assertTrue(result["repeated_openings"])
        self.assertTrue(result["is_repetitive"])

    def test_similar_sentence_structures_are_detected(self):
        text = " ".join(
            [
                "A young man is carefully placing red books on the wooden shelf.",
                "A young woman is carefully placing blue books on the wooden shelf.",
                "A young child is carefully placing green books on the wooden shelf.",
                "A young teacher is carefully placing old books on the wooden shelf.",
            ]
        )

        result = detect_repetitive_answer(text, "describe_image")

        self.assertTrue(result["similar_sentence_groups"])
        self.assertTrue(result["is_repetitive"])

    def test_short_repetitive_answer_cannot_receive_hard_zero(self):
        text = "There is a person. There is a person. There is a person."

        result = detect_repetitive_answer(text, "describe_image")

        self.assertFalse(result["is_repetitive"])
        self.assertLess(result["word_count"], result["minimum_words_for_zero"])

    def test_moderate_repetition_is_flagged_without_zero(self):
        repeated = "the chart clearly shows"
        text = (
            f"Analysts noted that {repeated} growth in regional employment. "
            f"Later evidence suggested {repeated} changes in public transport. "
            f"The speaker explained that {repeated} progress in school funding. "
            f"A separate survey found {repeated} movement in housing demand. "
            f"Finally the report stated {repeated} improvement in local services, "
            "while the remaining discussion introduced several distinct causes."
        )

        result = detect_repetitive_answer(text, "summarize_written_text")

        self.assertFalse(result["is_repetitive"])
        self.assertEqual(result["status"], "moderate")

    def test_profile_thresholds_can_be_overridden(self):
        text = " ".join([
            "The image repeatedly uses exactly the same prepared description."
        ] * 5)

        result = detect_repetitive_answer(
            text,
            "describe_image",
            config={
                "profiles": {
                    "brief_spoken": {"minimum_words": 200},
                },
            },
        )

        self.assertFalse(result["is_repetitive"])
        self.assertEqual(result["minimum_words_for_zero"], 200)

    def test_answer_type_can_select_a_different_profile(self):
        text = " ".join([
            "The image repeatedly uses exactly the same prepared description."
        ] * 5)

        result = detect_repetitive_answer(
            text,
            "describe_image",
            profile="brief_spoken",
            config={
                "answer_types": {"describe_image": "strict_review"},
                "profiles": {"strict_review": {"minimum_words": 200}},
            },
        )

        self.assertEqual(result["profile"], "strict_review")
        self.assertEqual(result["minimum_words_for_zero"], 200)
        self.assertFalse(result["is_repetitive"])

    def test_long_answer_with_occasional_harmless_repetition_passes(self):
        text = (
            "Education gives people practical knowledge and improves their ability "
            "to make informed decisions. For this reason communities often invest "
            "in schools, libraries, and teacher development. Students also benefit "
            "from meeting classmates with different experiences because discussion "
            "encourages patience and careful reasoning. Technology can support this "
            "process when it provides access to reliable materials rather than "
            "replacing thoughtful instruction. For this reason a balanced policy "
            "should combine digital resources with skilled teachers, suitable class "
            "sizes, and opportunities for independent work. Such an approach helps "
            "learners gain confidence while preparing for employment and civic life."
        )

        result = detect_repetitive_answer(text, "write_essay")

        self.assertFalse(result["is_repetitive"])

    def test_long_answer_dominated_by_one_template_triggers(self):
        sentence = (
            "This important issue clearly shows that people should work together "
            "to create a better future for everyone."
        )
        text = " ".join([sentence] * 8)

        result = detect_repetitive_answer(text, "write_essay")

        self.assertTrue(result["is_repetitive"])
        self.assertGreaterEqual(result["repetition_ratio"], 0.36)

    def test_speaking_and_writing_profiles_can_both_trigger(self):
        spoken = " ".join([
            "The picture clearly presents the same general feature in this scene."
        ] * 4)
        written = " ".join([
            "The argument repeatedly uses the same general claim without new evidence."
        ] * 9)

        spoken_result = detect_repetitive_answer(spoken, "describe_image")
        written_result = detect_repetitive_answer(written, "write_essay")

        self.assertTrue(spoken_result["is_repetitive"])
        self.assertTrue(written_result["is_repetitive"])

    def test_non_descriptive_contracts_do_not_opt_in(self):
        excluded = (
            "read_aloud",
            "repeat_sentence",
            "answer_short_question",
            "write_from_dictation",
            "mc_multiple",
            "fib_dropdown",
        )

        for subsection in excluded:
            with self.subTest(subsection=subsection):
                self.assertIsNone(
                    get_task_contract(subsection).repetition_profile
                )

    def test_score_override_preserves_assessment_and_zeros_scores(self):
        evaluation_result = {
            "ok": True,
            "evaluation": {
                "scores": {
                    "content": {"score": 5.0, "max": 6.0},
                    "grammar": {"score": 2.0, "max": 2.0},
                },
                "weighted_score": 7.0,
                "max_score": 8.0,
            },
        }
        detection = {
            "detector_version": "test-version",
            "is_repetitive": True,
            "reason": "Template-heavy answer.",
        }

        result = apply_repetition_score_override(evaluation_result, detection)

        self.assertEqual(result["evaluation"]["weighted_score"], 0.0)
        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 0.0)
        self.assertEqual(result["evaluation"]["scores"]["grammar"]["score"], 0.0)
        override = result["score_overrides"][0]
        self.assertEqual(override["code"], OVERRIDE_CODE)
        self.assertEqual(override["original_weighted_score"], 7.0)
        self.assertEqual(
            override["original_scores"]["content"]["score"],
            5.0,
        )

        reapplied = apply_repetition_score_override(result, detection)

        self.assertEqual(
            reapplied["score_overrides"][0]["original_weighted_score"],
            7.0,
        )
        self.assertEqual(
            reapplied["score_overrides"][0]["original_scores"]["content"][
                "score"
            ],
            5.0,
        )
        self.assertEqual(evaluation_result["evaluation"]["weighted_score"], 7.0)
