from unittest import TestCase

from examinor.services.known_answer_templates import (
    OVERRIDE_CODE,
    apply_known_template_score_override,
    detect_known_template_answer,
)
from examinor.services.repetitive_answer import apply_repetition_score_override


DESCRIBE_IMAGE_TEMPLATE = {
    "id": 1,
    "name": "Universal Describe Image",
    "version": "1",
    "template_text": (
        "The given image gives information regarding [[image heading]]. "
        "It is evident from the image that the highest maximum element from "
        "the picture is [[highest item]] for [[highest value]], whereas the "
        "lowest minimum element from the picture is [[lowest item]] for "
        "[[lowest value]]. All the details are represented in an organised "
        "manner which is easy for the viewer to comprehend and analyse. "
        "Moreover, it helps us understand the purpose of presentation very "
        "clearly. Overall, it is an informative image and can be used for "
        "future reference."
    ),
    "minimum_match_ratio": 0.60,
    "maximum_original_words": 24,
    "minimum_matched_words": 35,
    "minimum_match_blocks": 3,
}


class KnownAnswerTemplateTests(TestCase):
    def test_template_dominated_answer_receives_hard_zero_decision(self):
        answer = (
            "The given image gives information regarding monthly sales. "
            "It is evident from the image that the highest maximum element from "
            "the picture is phones for eighty, whereas the lowest minimum element "
            "from the picture is tablets for twenty. All the details are "
            "represented in an organised manner which is easy for the viewer to "
            "comprehend and analyse. Moreover, it helps us understand the purpose "
            "of presentation very clearly. Overall, it is an informative image "
            "and can be used for future reference."
        )

        result = detect_known_template_answer(
            answer,
            [DESCRIBE_IMAGE_TEMPLATE],
            "describe_image",
        )

        self.assertTrue(result["is_template_dominated"])
        self.assertEqual(result["status"], "hard_zero")
        self.assertGreater(result["answer_match_ratio"], 0.60)
        self.assertLessEqual(result["original_word_count"], 24)

    def test_framework_with_substantial_original_content_is_allowed(self):
        answer = (
            "The given image gives information regarding regional employment. "
            "The horizontal axis covers five years from 2020 to 2024, while the "
            "vertical axis records the number of employed residents in thousands. "
            "Employment rose steadily during the first three years, briefly fell "
            "when two factories closed, and then recovered strongly in 2024. "
            "The technology sector contributed most of the final increase, while "
            "retail remained almost unchanged. Younger workers experienced the "
            "largest improvement, although the oldest group continued to have the "
            "lowest participation rate. Overall, it is an informative image and "
            "can be used for future reference."
        )

        result = detect_known_template_answer(
            answer,
            [DESCRIBE_IMAGE_TEMPLATE],
            "describe_image",
        )

        self.assertFalse(result["is_template_dominated"])
        self.assertGreater(result["original_word_count"], 24)

    def test_one_common_template_sentence_is_not_enough(self):
        answer = (
            "The given image gives information regarding city transport. The bus "
            "network expands through six districts and connects hospitals, schools, "
            "and residential areas. Passenger numbers rise sharply in the morning "
            "before declining after nine o'clock. The eastern route is busiest, but "
            "the airport service covers the greatest distance."
        )

        result = detect_known_template_answer(
            answer,
            [DESCRIBE_IMAGE_TEMPLATE],
            "describe_image",
        )

        self.assertFalse(result["is_template_dominated"])
        self.assertFalse(result["template_usage_detected"])

    def test_unrelated_answer_passes(self):
        answer = (
            "A crowded station occupies the centre of the photograph. Commuters "
            "wait beneath a digital timetable while two employees assist an older "
            "passenger near the ticket desk. Natural light enters through the roof, "
            "and the scene suggests an ordinary weekday journey."
        )

        result = detect_known_template_answer(
            answer,
            [DESCRIBE_IMAGE_TEMPLATE],
            "describe_image",
        )

        self.assertFalse(result["is_template_dominated"])
        self.assertEqual(result["status"], "pass")

    def test_score_override_is_auditable(self):
        evaluation_result = {
            "ok": True,
            "evaluation": {
                "scores": {
                    "content": {"score": 5.0, "max": 6.0},
                    "oral_fluency": {"score": 4.0, "max": 5.0},
                },
                "weighted_score": 9.0,
                "max_score": 11.0,
            },
        }
        detection = {
            "detector_version": "test",
            "is_template_dominated": True,
            "reason": "Template dominates the response.",
        }

        result = apply_known_template_score_override(
            evaluation_result,
            detection,
        )

        self.assertEqual(result["evaluation"]["weighted_score"], 0.0)
        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 0.0)
        self.assertEqual(result["score_overrides"][0]["code"], OVERRIDE_CODE)
        self.assertEqual(
            result["score_overrides"][0]["original_weighted_score"],
            9.0,
        )
        self.assertIn("known_template", result["integrity_checks"])

    def test_multiple_integrity_gates_preserve_original_provider_score(self):
        evaluation_result = {
            "ok": True,
            "evaluation": {
                "scores": {"content": {"score": 5.0, "max": 6.0}},
                "weighted_score": 5.0,
                "max_score": 6.0,
            },
        }
        repetition = {
            "detector_version": "repetition-test",
            "is_repetitive": True,
            "reason": "Repeated answer.",
        }
        known_template = {
            "detector_version": "template-test",
            "is_template_dominated": True,
            "reason": "Known template dominates the answer.",
        }

        result = apply_repetition_score_override(
            evaluation_result,
            repetition,
        )
        result = apply_known_template_score_override(result, known_template)

        self.assertEqual(result["evaluation"]["weighted_score"], 0.0)
        self.assertEqual(len(result["score_overrides"]), 2)
        for override in result["score_overrides"]:
            self.assertEqual(override["original_weighted_score"], 5.0)
            self.assertEqual(
                override["original_scores"]["content"]["score"],
                5.0,
            )
