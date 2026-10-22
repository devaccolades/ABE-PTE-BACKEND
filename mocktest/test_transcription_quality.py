from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import soundfile as sf
from django.test import SimpleTestCase, TestCase, override_settings

from examinor.services.evaluation_context import EvaluationContextError, validate_evaluation_context
from mocktest.services.transcription import transcribe_and_analyse, transcribe_audio
from mocktest.services.transcription_quality import (
    TranscriptionReliabilityError, inspect_transcription_quality,
)
from mocktest.models import (
    MockTest, MockTestSection, Question, Section, SingleResponse, SubSection,
    UserMockTestSession, UserResponse,
)
from mocktest.tasks import EvaluationTaskFailed, transcribe_single_task, transcribe_task


class TranscriptionQualityTests(SimpleTestCase):
    def test_low_confidence_alone_does_not_reject_poorly_pronounced_speech(self):
        quality = inspect_transcription_quality("some spoken words", [{
            "text": "some spoken words", "avg_logprob": -1.4, "no_speech_prob": 0.01,
        }])
        self.assertFalse(quality["requires_review"])

    def test_strong_joint_silence_and_confidence_warning_requires_review(self):
        text = "This may have been guessed."
        quality = inspect_transcription_quality(text, [{
            "text": text, "avg_logprob": -1.5, "no_speech_prob": 0.95,
        }])
        self.assertTrue(quality["requires_review"])
        self.assertEqual(quality["raw_transcript"], text)
        self.assertEqual(quality["suspicious_segment_indices"], [0])

    def test_one_suspicious_segment_is_not_hidden_by_confident_segments(self):
        quality = inspect_transcription_quality("real speech plus guessed words", [
            {"text": "real speech", "avg_logprob": -0.1, "no_speech_prob": 0.01},
            {"text": "guessed words", "avg_logprob": -1.5, "no_speech_prob": 0.95},
        ])
        self.assertTrue(quality["requires_review"])
        self.assertEqual(len(quality["segments"]), 2)

    def test_absent_metrics_and_legitimate_repetition_are_not_rejected(self):
        for segments in ([], [{"text": "we we need to talk"}], [SimpleNamespace(
            text="we we need to talk", avg_logprob=-0.1, no_speech_prob=0.01,
            compression_ratio=3.0,
        )]):
            self.assertFalse(inspect_transcription_quality("we we need to talk", segments)["requires_review"])

    @override_settings(TRANSCRIPTION_RELIABILITY_CONFIG={"no_speech_threshold": 0.99})
    def test_reliability_threshold_can_be_tuned(self):
        self.assertFalse(inspect_transcription_quality("some words", [{
            "text": "some words", "avg_logprob": -1.5, "no_speech_prob": 0.95,
        }])["requires_review"])

    def test_saved_suspicious_transcript_is_not_sent_for_evaluation(self):
        with self.assertRaises(EvaluationContextError) as caught:
            validate_evaluation_context("read_aloud", {"transcribed_audio_data": {
                "transcription": {"text": "guessed words"},
                "transcription_quality": {"requires_review": True},
            }})
        self.assertEqual(caught.exception.code, "unreliable_transcription")

    @patch("mocktest.services.transcription._transcribe_audio_with_evidence")
    def test_digital_silence_is_not_transcribed(self, transcribe):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "silence.wav"
            sf.write(path, np.zeros(16000), 16000)
            with self.assertRaises(TranscriptionReliabilityError) as caught:
                transcribe_and_analyse(str(path))
        self.assertTrue(caught.exception.report["transcription_quality"]["requires_review"])
        transcribe.assert_not_called()

    @patch("mocktest.services.transcription._transcribe_audio_with_evidence")
    def test_pipeline_holds_suspicious_text_without_deleting_or_grading_it(self, transcribe):
        transcribe.return_value = ("guessed words", [], [{
            "text": "guessed words", "avg_logprob": -1.5, "no_speech_prob": 0.95,
        }])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recording.wav"
            sf.write(path, np.sin(np.arange(16000) * 0.1) * 0.1, 16000)
            with self.assertRaises(TranscriptionReliabilityError) as caught:
                transcribe_and_analyse(str(path))
        self.assertEqual(caught.exception.report["transcription"]["text"], "guessed words")

    @patch("mocktest.services.transcription._transcribe_audio_with_evidence")
    def test_reliable_pipeline_retains_recognition_evidence_and_candidate_words(self, transcribe):
        text = "we we need to talk"
        transcribe.return_value = (text, [
            {"word": word, "start": index * 0.4, "end": (index + 1) * 0.4}
            for index, word in enumerate(text.split())
        ], [{"text": text, "start": 0, "end": 2, "avg_logprob": -0.2, "no_speech_prob": 0.01}])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recording.wav"
            sf.write(path, np.sin(np.arange(32000) * 0.1) * 0.1, 16000)
            report = transcribe_and_analyse(str(path))
        self.assertFalse(report["transcription_quality"]["requires_review"])
        self.assertEqual(report["transcription_quality"]["raw_transcript"], text)
        self.assertEqual(report["transcription"]["text"], text)
        self.assertEqual(report["fluency_analysis"]["num_repetitions"], 1)

    @override_settings(OPENAI_WHISPER_API_KEY="fake-test-key", OPENAI_TRANSCRIPTION_MODEL="whisper-1")
    @patch("mocktest.services.transcription.OpenAI")
    def test_english_request_has_no_answer_key_hint_and_keeps_public_tuple(self, client):
        client.return_value.audio.transcriptions.create.return_value = SimpleNamespace(
            text="candidate words", words=[], segments=[],
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recording.wav"
            sf.write(path, np.zeros(16000), 16000)
            self.assertEqual(transcribe_audio(str(path)), ("candidate words", []))
        kwargs = client.return_value.audio.transcriptions.create.call_args.kwargs
        self.assertEqual(kwargs["language"], "en")
        self.assertNotIn("prompt", kwargs)


class TranscriptionFailureTaskTests(TestCase):
    @patch("mocktest.tasks.subprocess.run")
    @patch("mocktest.tasks.transcribe_and_analyse")
    def test_both_tasks_persist_review_evidence_without_retry_or_score(self, transcribe, convert):
        report = {"transcription_quality": inspect_transcription_quality("guessed words", [{
            "text": "guessed words", "avg_logprob": -1.5, "no_speech_prob": 0.95,
        }])}
        transcribe.side_effect = TranscriptionReliabilityError(report)
        section = Section.objects.create(name="Speaking")
        subsection = SubSection.objects.create(
            section=section, name="repeat_sentence", evaluation_type="ai", ai_input_type="audio",
        )
        paper = MockTest.objects.create(title="Transcription review QA")
        paper_section = MockTestSection.objects.create(mock_test=paper, section=section, order=1)
        question = Question.objects.create(name="QA", subsection=subsection, mock_test_section=paper_section)
        session = UserMockTestSession.objects.create(mock_test=paper, name="QA", session_id="quality-qa")
        common = {"question": question, "answer_audio": "qa/recording.webm"}
        rows = (
            (SingleResponse.objects.create(name="QA", **common), transcribe_single_task),
            (UserResponse.objects.create(mock_test=paper, user_session=session, **common), transcribe_task),
        )
        for response, task in rows:
            with self.subTest(model=type(response).__name__):
                result = task.apply(args=(response.pk,))
                self.assertTrue(result.failed())
                self.assertIsInstance(result.result, EvaluationTaskFailed)
                response.refresh_from_db()
                self.assertFalse(response.evaluated)
                self.assertEqual(response.evaluation_status, "failed")
                self.assertEqual(response.evaluation_result["code"], "unreliable_transcription")
                self.assertFalse(response.evaluation_result["retryable"])
                self.assertEqual(response.evaluation_result["transcription_report"], report)
