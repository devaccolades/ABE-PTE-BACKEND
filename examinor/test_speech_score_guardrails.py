from django.test import SimpleTestCase

from examinor.scoring.validators import validate_and_normalize_language_feedback
from examinor.services.speech_score_guardrails import apply_speech_score_guardrails


class SpeechScoreGuardrailTests(SimpleTestCase):
    def test_repeat_sentence_caps_unrelated_content_and_inflated_speech_scores(self):
        evaluation = {
            "scores": {
                "content": {"score": 3.0, "max": 3.0},
                "oral_fluency": {"score": 5.0, "max": 5.0},
                "pronunciation": {"score": 5.0, "max": 5.0},
            },
            "weighted_score": 13.0,
        }
        payload = {
            "transcribed_audio_data": {
                "analysis_version": "speech-evidence-v2",
                "transcription": {"text": "This answer is entirely unrelated"},
                "fluency_analysis": {"overall_score_0_to_5": 2},
                "pronunciation_analysis": {"overall_score_0_to_5": 3},
            }
        }

        result = apply_speech_score_guardrails(
            evaluation,
            task_type="repeat_sentence",
            question_text="Students must submit the assignment before Friday",
            evaluation_payload=payload,
        )

        self.assertEqual(result["scores"]["content"]["score"], 0.0)
        self.assertEqual(result["scores"]["oral_fluency"]["score"], 2.0)
        self.assertEqual(result["scores"]["pronunciation"]["score"], 3.0)
        self.assertEqual(result["weighted_score"], 5.0)
        self.assertEqual(len(result["score_guardrails"]), 3)

    def test_exact_repeat_sentence_keeps_full_content(self):
        sentence = "Students must submit the assignment before Friday"
        evaluation = {
            "scores": {"content": {"score": 3.0, "max": 3.0}},
            "weighted_score": 3.0,
        }
        payload = {"transcribed_audio_data": {"transcription": {"text": sentence}}}

        result = apply_speech_score_guardrails(
            evaluation,
            task_type="repeat_sentence",
            question_text=sentence,
            evaluation_payload=payload,
        )

        self.assertEqual(result, evaluation)

    def test_legacy_placeholder_analytics_are_not_used_for_speech_caps(self):
        evaluation = {
            "scores": {"oral_fluency": {"score": 5.0, "max": 5.0}},
            "weighted_score": 5.0,
        }
        payload = {
            "transcribed_audio_data": {
                "fluency_analysis": {"overall_score_0_to_5": 1},
            }
        }

        result = apply_speech_score_guardrails(
            evaluation,
            task_type="describe_image",
            question_text="Describe the image",
            evaluation_payload=payload,
        )

        self.assertEqual(result, evaluation)


class LanguageScoreConsistencyTests(SimpleTestCase):
    def test_full_grammar_score_is_rejected_when_grammar_error_is_reported(self):
        valid, _, error = validate_and_normalize_language_feedback(
            {
                "ok": True,
                "evaluation": {
                    "scores": {"grammar": {"score": 2.0, "max": 2.0}},
                    "feedback": {
                        "errors": [{
                            "type": "grammar",
                            "text": "highlight",
                            "suggestion": "highlights",
                            "explanation": "Subject-verb agreement.",
                        }],
                    },
                },
            },
            "Participation highlight the issue.",
        )

        self.assertFalse(valid)
        self.assertIn("Grammar is at maximum", error)
