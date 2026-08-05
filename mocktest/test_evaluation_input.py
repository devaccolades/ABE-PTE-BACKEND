from types import SimpleNamespace

from django.test import SimpleTestCase

from mocktest.services.evaluation_input import (
    MISSING_RESPONSE_AUDIO_CODE,
    question_requires_audio,
    response_input_issue,
)


def question_for(subsection_name, configured_input_type):
    return SimpleNamespace(
        subsection=SimpleNamespace(
            name=subsection_name,
            ai_input_type=configured_input_type,
        )
    )


def response_for(question, *, audio=None, transcript=None):
    return SimpleNamespace(
        question=question,
        answer_audio=audio,
        transcribed_audio_data=transcript,
    )


class EvaluationInputContractTests(SimpleTestCase):
    def test_task_contract_overrides_editable_audio_setting(self):
        read_aloud = question_for("read_aloud", "text")
        write_essay = question_for("write_essay", "audio")

        self.assertTrue(question_requires_audio(read_aloud))
        self.assertFalse(question_requires_audio(write_essay))

    def test_missing_audio_is_non_retryable_without_replacement_input(self):
        response = response_for(question_for("repeat_sentence", "text"))

        issue = response_input_issue(response)

        self.assertEqual(issue.code, MISSING_RESPONSE_AUDIO_CODE)
        self.assertFalse(issue.retryable)
        self.assertEqual(
            issue.as_result(),
            {
                "ok": False,
                "stage": "submission",
                "code": "response_audio_missing",
                "error": issue.message,
                "retryable": False,
            },
        )

    def test_stored_audio_or_transcript_is_recoverable_input(self):
        question = question_for("describe_image", "text")
        stored_audio = SimpleNamespace(name="response/audio/answer.webm")

        self.assertIsNone(
            response_input_issue(response_for(question, audio=stored_audio))
        )
        self.assertIsNone(
            response_input_issue(
                response_for(
                    question,
                    transcript={"transcription": {"text": "Spoken answer"}},
                )
            )
        )
