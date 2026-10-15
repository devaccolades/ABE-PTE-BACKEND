from django.test import SimpleTestCase

from examinor.scoring.score_calculator import compile_skill_scores
from examinor.services.speech_score_guardrails import apply_speech_score_guardrails


class RepeatSentenceReferenceTests(SimpleTestCase):
    sentence = "We will change the classroom because this one is too small."

    def evaluate(self, *, question_text, reference=None, answer=None, task="repeat_sentence"):
        payload = {
            "transcribed_audio_data": {
                "transcription": {"text": self.sentence if answer is None else answer},
            },
            "reference_answer": reference,
        }
        return apply_speech_score_guardrails(
            {
                "scores": {
                    "content": {"max": 3, "score": 3},
                    "oral_fluency": {"max": 5, "score": 3},
                    "pronunciation": {"max": 5, "score": 3},
                },
                "weighted_score": 9,
            },
            task_type=task,
            question_text=question_text,
            evaluation_payload=payload,
        )

    def gate(self, result):
        return compile_skill_scores(
            result["scores"],
            {
                "content": ["listening", "speaking"],
                "oral_fluency": ["speaking"],
                "pronunciation": ["speaking"],
            },
            {"listening": 1.5, "speaking": 1.2},
            gate_traits=("content",),
        )["gate"]

    def test_response_273_correct_reference_with_empty_question_text_is_not_gated(self):
        result = self.evaluate(
            question_text="",
            reference=self.sentence,
            answer=self.sentence.rstrip("."),
        )
        self.assertEqual(result["scores"]["content"]["score"], 3)
        self.assertEqual(result["weighted_score"], 9)
        self.assertFalse(self.gate(result)["applied"])

    def test_reference_takes_priority_over_task_instructions(self):
        result = self.evaluate(
            question_text="Listen to the audio and repeat the sentence.",
            reference=self.sentence,
        )
        self.assertEqual(result["scores"]["content"]["score"], 3)
        self.assertFalse(self.gate(result)["applied"])

    def test_unrelated_answer_still_triggers_content_gate(self):
        unrelated = "Purple elephants dance beneath silver clouds."
        result = self.evaluate(
            question_text=unrelated,
            reference=self.sentence,
            answer=unrelated,
        )
        self.assertEqual(result["scores"]["content"]["score"], 0)
        self.assertTrue(self.gate(result)["applied"])
        evidence = result["score_guardrails"][0]["evidence"]
        self.assertEqual(evidence["reference_source"], "reference_answer")

    def test_question_text_is_fallback_when_no_reference_is_configured(self):
        for reference in (None, "", "  "):
            with self.subTest(reference=reference):
                result = self.evaluate(question_text=self.sentence, reference=reference)
                self.assertEqual(result["scores"]["content"]["score"], 3)
                self.assertFalse(self.gate(result)["applied"])

    def test_read_aloud_still_uses_the_displayed_question_text(self):
        result = self.evaluate(
            task="read_aloud",
            question_text=self.sentence,
            reference="Unrelated optional reference text.",
        )
        self.assertEqual(result["scores"]["content"]["score"], 3)
