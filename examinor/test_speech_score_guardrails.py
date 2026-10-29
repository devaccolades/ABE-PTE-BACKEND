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


class ReadAloudContentBandTests(SimpleTestCase):
    # 20 words, so each word is 5% of the passage.
    PASSAGE = (
        "one two three four five six seven eight nine ten "
        "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
    )

    def content_after_cap(self, transcript, model_score=6.0):
        result = apply_speech_score_guardrails(
            {"scores": {"content": {"score": model_score, "max": 6.0}}, "weighted_score": model_score},
            task_type="read_aloud",
            question_text=self.PASSAGE,
            evaluation_payload={"transcribed_audio_data": {"transcription": {"text": transcript}}},
        )
        return result["scores"]["content"]["score"]

    def test_bands_follow_the_share_of_prompt_words_read(self):
        words = self.PASSAGE.split()
        for count, band in ((20, 6), (18, 6), (17, 5), (15, 5), (12, 4), (9, 3), (8, 2), (6, 2), (3, 1), (2, 0)):
            with self.subTest(read=count):
                self.assertEqual(self.content_after_cap(" ".join(words[:count])), band)

    def test_half_a_reading_is_not_credited_as_more_than_half(self):
        half = " ".join(self.PASSAGE.split()[:9])  # 45%: band 3, the old ratio allowed 4
        self.assertEqual(self.content_after_cap(half), 3.0)

    def test_hesitations_do_not_reduce_content_and_the_model_score_is_not_raised(self):
        transcript = self.PASSAGE.replace("five", "um five").replace("twelve", "uh twelve")
        self.assertEqual(self.content_after_cap(transcript), 6.0)
        self.assertEqual(self.content_after_cap(self.PASSAGE, model_score=4.0), 4.0)


class LenientLanguageAnnotationTests(SimpleTestCase):
    def evaluation(self, grammar, spelling, errors):
        return {"ok": True, "evaluation": {
            "scores": {"grammar": {"score": grammar, "max": 2}, "spelling": {"score": spelling, "max": 2}},
            "feedback": {"summary": "Feedback.", "errors": errors},
        }}

    def test_strict_mode_still_rejects_mismatches_for_a_repair(self):
        valid, _, error = validate_and_normalize_language_feedback(
            self.evaluation(1, 2, []), "The answer is fine.",
        )
        self.assertFalse(valid)
        self.assertIn("Grammar is below maximum", error)

    def test_after_repair_mismatches_keep_scores_and_are_recorded(self):
        answer = "The answr is mostly fine."
        errors = [
            {"type": "spelling", "text": "answr", "suggestion": "answer"},
            {"type": "spelling", "text": "not in the answer", "suggestion": "x"},
            {"type": "grammar", "text": "is mostly", "suggestion": "is"},
        ]
        valid, normalized, error = validate_and_normalize_language_feedback(
            self.evaluation(1, 2, errors), answer, strict=False,
        )
        self.assertTrue(valid, error)
        feedback = normalized["evaluation"]["feedback"]
        self.assertEqual(normalized["evaluation"]["scores"]["grammar"]["score"], 1)
        self.assertEqual(normalized["evaluation"]["scores"]["spelling"]["score"], 2)
        # Spelling is at full marks, so its annotations are not shown to the student.
        self.assertEqual([e["type"] for e in feedback["errors"]], ["grammar"])
        self.assertEqual(len(feedback["annotation_issues"]), 2)

    def test_after_repair_a_lowered_score_without_annotation_is_kept(self):
        valid, normalized, _ = validate_and_normalize_language_feedback(
            self.evaluation(1, 2, []), "The answer is fine.", strict=False,
        )
        self.assertTrue(valid)
        self.assertEqual(normalized["evaluation"]["scores"]["grammar"]["score"], 1)
        self.assertIn("Grammar is below maximum", normalized["evaluation"]["feedback"]["annotation_issues"][0])
