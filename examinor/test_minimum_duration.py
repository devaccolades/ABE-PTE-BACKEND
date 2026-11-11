from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from examinor.services.minimum_duration import (
    apply_minimum_duration_policy,
    inspect_minimum_duration,
)
from examinor.services.orchestrator import run_evaluation_for_subsection


SGD = "summarise_group_discussion"
ANSWER = "The speakers discussed whether physical education should be compulsory at university."


def payload(duration):
    return {
        "transcribed_audio_data": {
            "audio_metadata": {"duration_seconds": duration},
            "transcription": {"text": ANSWER},
        },
        "reference_answer": "Speaker one: physical education should be optional.",
    }


def positive_result():
    return {
        "ok": True,
        "evaluation": {
            "scores": {
                "content": {"score": 5, "max": 6},
                "oral_fluency": {"score": 4, "max": 5},
                "pronunciation": {"score": 4, "max": 5},
            },
            "weighted_score": 13,
            "max_score": 16,
            "feedback": {"summary": "Covers all three speakers.", "errors": []},
        },
    }


class MinimumDurationDetectionTests(SimpleTestCase):
    def test_group_discussion_under_fifty_seconds_is_too_short(self):
        detection = inspect_minimum_duration(SGD, payload(49.9))

        self.assertTrue(detection["is_too_short"])
        self.assertIn("at least 50 seconds", detection["reason"])
        self.assertIn("this recording is 49 seconds", detection["reason"])

    def test_fifty_seconds_or_more_is_allowed(self):
        for duration in (50, 50.0, 119.6):
            with self.subTest(duration=duration):
                detection = inspect_minimum_duration(SGD, payload(duration))
                self.assertTrue(detection["applicable"])
                self.assertFalse(detection["is_too_short"])

    def test_no_zero_without_a_usable_measured_length(self):
        for duration in (None, 0, -3, float("nan"), "30", True):
            with self.subTest(duration=duration):
                detection = inspect_minimum_duration(SGD, payload(duration))
                self.assertFalse(detection["applicable"])
                self.assertFalse(detection["is_too_short"])
        self.assertFalse(inspect_minimum_duration(SGD, {"answer_data": ANSWER})["applicable"])

    def test_other_speaking_tasks_have_no_minimum(self):
        for task in ("retell_lecture", "describe_image", "respond_to_a_situation", "read_aloud"):
            with self.subTest(task=task):
                self.assertFalse(inspect_minimum_duration(task, payload(10))["applicable"])

    @override_settings(MINIMUM_DURATION_POLICY_ENABLED=False)
    def test_policy_can_be_switched_off(self):
        detection = inspect_minimum_duration(SGD, payload(10))

        self.assertFalse(detection["enabled"])
        self.assertFalse(detection["is_too_short"])

    def test_final_policy_zeroes_a_positive_result_and_explains_why(self):
        result = apply_minimum_duration_policy(positive_result(), SGD, payload(32.4))

        self.assertTrue(all(trait["score"] == 0 for trait in result["evaluation"]["scores"].values()))
        self.assertEqual(result["score_overrides"][0]["code"], "company_minimum_duration")
        self.assertIn("32 seconds", result["evaluation"]["feedback"]["summary"])
        self.assertTrue(result["integrity_checks"]["minimum_duration"]["is_too_short"])

    def test_final_policy_keeps_scores_for_a_long_enough_recording(self):
        result = apply_minimum_duration_policy(positive_result(), SGD, payload(85))

        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 5)
        self.assertNotIn("score_overrides", result)
        self.assertFalse(result["integrity_checks"]["minimum_duration"]["is_too_short"])


class MinimumDurationGateTests(TestCase):
    subsection = SimpleNamespace(
        name=SGD,
        rubric={"content": {"max": 6}, "oral_fluency": {"max": 5}, "pronunciation": {"max": 5}},
    )

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_short_recording_is_zeroed_before_the_provider_is_called(self, provider):
        result = run_evaluation_for_subsection(self.subsection, "Summarise the discussion.", payload(41))

        self.assertTrue(result["ok"])
        self.assertFalse(result["provider_called"])
        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        self.assertEqual(result["score_overrides"][0]["code"], "company_minimum_duration")
        provider.assert_not_called()

    @patch(
        "examinor.services.orchestrator.evaluate_with_openai",
        side_effect=RuntimeError("provider reached"),
    )
    def test_long_enough_recording_goes_to_the_examiner(self, provider):
        try:
            run_evaluation_for_subsection(self.subsection, "Summarise the discussion.", payload(64))
        except RuntimeError:
            pass

        provider.assert_called()
