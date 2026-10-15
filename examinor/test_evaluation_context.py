import base64
import hashlib
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from examinor.models import EvaluationCache
from examinor.services.evaluation_context import (
    EvaluationContextError,
    question_source_payload,
    validate_evaluation_context,
)
from examinor.services.evaluator import evaluate_with_openai
from examinor.services.orchestrator import run_evaluation_for_subsection
from examinor.services.prompt_builder import build_prompt, evaluation_answer_text
from mocktest.forms import MockTestAdminForm
from mocktest.models import (
    MockTest, MockTestSection, Question, Section, SingleResponse, SubSection,
    UserMockTestSession, UserResponse,
)
from mocktest.services.question_bank_validation import QuestionBankAuditor
from mocktest.tasks import evaluate_single_response, evaluate_user_response


def image_data(colour="red"):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def image_url(colour="red"):
    return "data:image/png;base64," + base64.b64encode(image_data(colour)).decode("ascii")


def provider_result(score=2):
    return {"success": True, "data": {"scores": {"content": {"score": score, "max": 3}}}}


class CandidateAnswerContextTests(SimpleTestCase):
    def test_all_accepted_transcript_shapes_reach_the_candidate_block(self):
        for transcript in (
            "This is the spoken answer.",
            {"transcription": "This is the spoken answer."},
            {"transcription": {"text": "This is the spoken answer."}},
            {"text": "This is the spoken answer."},
        ):
            with self.subTest(transcript=transcript):
                payload = {"transcribed_audio_data": transcript, "answer_data": "Other text"}
                self.assertEqual(evaluation_answer_text(payload), "This is the spoken answer.")
                prompt, _ = build_prompt("read_aloud", "Read the passage", payload, {"content": {"max": 3}})
                self.assertIn('CANDIDATE_RESPONSE:\n"""This is the spoken answer."""', prompt)

    def test_absent_answer_is_rejected_even_when_reference_is_present(self):
        with self.assertRaises(EvaluationContextError) as caught:
            validate_evaluation_context("retell_lecture", {"reference_answer": "The source lecture."})
        self.assertEqual(caught.exception.code, "missing_candidate_answer")

    def test_different_answers_references_and_images_produce_different_cache_keys(self):
        hashes = set()
        for answer, reference, colour in (
            ("First answer", "First reference", "red"),
            ("Other answer", "First reference", "red"),
            ("First answer", "Other reference", "red"),
            ("First answer", "First reference", "blue"),
        ):
            payload, evidence = validate_evaluation_context("describe_image", {
                "answer_data": answer, "reference_answer": reference, "question_image": image_url(colour),
            })
            prompt, prompt_hash = build_prompt("describe_image", "Describe the chart", payload, {"content": {"max": 3}})
            self.assertNotIn(payload["question_image"]["data_url"], prompt)
            self.assertIn(evidence["question_image_sha256"], prompt)
            hashes.add(prompt_hash)
        self.assertEqual(len(hashes), 4)

    def test_missing_corrupt_and_remote_images_are_rejected(self):
        for raw_image in (None, "https://example.com/chart.png", "data:image/png;base64,!!!", "data:image/png;base64,YmFk"):
            with self.subTest(raw_image=raw_image):
                with self.assertRaises(EvaluationContextError):
                    validate_evaluation_context("describe_image", {"answer_data": "A chart", "question_image": raw_image})

    def test_image_is_read_from_storage_without_a_local_path(self):
        storage = Mock()
        storage.open.return_value = BytesIO(image_data())
        question = SimpleNamespace(
            correct_answer="Chart key points",
            subsection=SimpleNamespace(name="describe_image"),
            image=SimpleNamespace(name="questions/chart.png", storage=storage),
        )
        payload = question_source_payload(question)
        storage.open.assert_called_once_with("questions/chart.png", "rb")
        self.assertEqual(payload["reference_answer"], "Chart key points")
        self.assertEqual(payload["question_image"]["sha256"], hashlib.sha256(image_data()).hexdigest())


@override_settings(OPENAI_API_KEY="test-key", OPENAI_EVALUATION_MODEL="gpt-5-nano")
class ProviderImageInputTests(SimpleTestCase):
    @patch("examinor.services.evaluator.get_openai_client")
    def test_actual_image_is_attached_to_the_provider_request(self, get_client):
        get_client.return_value.responses.create.return_value.output_text = json.dumps(provider_result()["data"])
        result = evaluate_with_openai("Candidate answer and source prompt", "hash", image_data_url=image_url())
        self.assertTrue(result["success"])
        provider_input = get_client.return_value.responses.create.call_args.kwargs["input"]
        self.assertEqual(provider_input[0]["content"], [
            {"type": "input_text", "text": "Candidate answer and source prompt"},
            {"type": "input_image", "image_url": image_url(), "detail": "high"},
        ])

    @patch("examinor.services.evaluator.get_openai_client")
    def test_text_tasks_keep_the_existing_provider_request(self, get_client):
        get_client.return_value.responses.create.return_value.output_text = json.dumps(provider_result()["data"])
        evaluate_with_openai("Candidate answer", "hash")
        self.assertEqual(get_client.return_value.responses.create.call_args.kwargs["input"], "Candidate answer")


@override_settings(OPENAI_EVALUATION_MODEL="gpt-5-nano")
class GroundedEvaluationTests(TestCase):
    def setUp(self):
        self.section = Section.objects.create(name="Speaking")

    def subsection(self, name):
        return SubSection.objects.create(
            section=self.section, name=name, evaluation_type="ai",
            rubric={"content": {"max": 3}}, trait_skill_map={"content": ["speaking"]},
        )

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_source_based_tasks_reject_missing_references_before_ai_or_cache(self, evaluate):
        for name in ("retell_lecture", "summarise_group_discussion", "summarize_spoken_text"):
            with self.subTest(task=name):
                result = run_evaluation_for_subsection(self.subsection(name), "Task instruction", {
                    "answer_data": "The candidate's summary", "reference_answer": "  ",
                })
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "missing_ai_reference")
                self.assertFalse(result["retryable"])
        evaluate.assert_not_called()
        self.assertEqual(EvaluationCache.objects.count(), 0)

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_valid_lecture_reference_and_candidate_are_both_sent(self, evaluate):
        evaluate.return_value = provider_result()
        result = run_evaluation_for_subsection(self.subsection("retell_lecture"), "Retell the lecture", {
            "transcribed_audio_data": {"transcription": "Candidate's actual spoken summary"},
            "reference_answer": "Source lecture about climate adaptation",
        })
        self.assertTrue(result["ok"])
        prompt = evaluate.call_args.args[0]
        self.assertIn("Candidate's actual spoken summary", prompt)
        self.assertIn("Source lecture about climate adaptation", prompt)
        self.assertIsNotNone(result["input_context"]["reference_answer_sha256"])

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_image_is_preserved_during_validation_repairs(self, evaluate):
        evaluate.side_effect = [provider_result(score=9), provider_result(score=2)]
        result = run_evaluation_for_subsection(self.subsection("describe_image"), "Describe the chart", {
            "transcribed_audio_data": {"transcription": {"text": "The chart shows sales."}},
            "question_image": image_url(),
        })
        self.assertTrue(result["ok"])
        self.assertEqual(evaluate.call_count, 2)
        for call in evaluate.call_args_list:
            self.assertEqual(call.kwargs["image_data_url"], image_url())
        self.assertIsNotNone(result["input_context"]["question_image_sha256"])

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_changed_image_cannot_reuse_previous_image_evaluation(self, evaluate):
        evaluate.return_value = provider_result()
        subsection = self.subsection("describe_image")
        payload = {"answer_data": "The image shows sales", "question_image": image_url()}
        first = run_evaluation_for_subsection(subsection, "Describe the chart", payload)
        cached = run_evaluation_for_subsection(subsection, "Describe the chart", payload)
        changed = run_evaluation_for_subsection(subsection, "Describe the chart", {**payload, "question_image": image_url("blue")})
        self.assertTrue(cached["cached"])
        self.assertEqual(first["prompt_hash"], cached["prompt_hash"])
        self.assertNotEqual(first["prompt_hash"], changed["prompt_hash"])
        self.assertEqual(evaluate.call_count, 2)

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_diagnostic_endpoint_accepts_spoken_string_and_reference(self, evaluate):
        self.subsection("retell_lecture")
        evaluate.return_value = provider_result()
        response = APIClient().post("/exam/test/", {
            "subsection_name": "retell_lecture", "question_text": "Retell the lecture",
            "audio_text": "Actual spoken answer", "reference_answer": "Original lecture key points",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertIn('CANDIDATE_RESPONSE:\n"""Actual spoken answer"""', evaluate.call_args.args[0])

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_diagnostic_endpoint_rejects_absent_answer_and_source(self, evaluate):
        self.subsection("retell_lecture")
        for extra, code in (({}, "missing_candidate_answer"), ({"audio_text": "An answer"}, "missing_ai_reference")):
            response = APIClient().post("/exam/test/", {
                "subsection_name": "retell_lecture", "question_text": "Retell the lecture", **extra,
            }, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["code"], code)
        evaluate.assert_not_called()

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_diagnostic_spoken_answer_receives_exam_content_guardrails(self, evaluate):
        self.subsection("repeat_sentence")
        evaluate.return_value = provider_result(score=3)
        response = APIClient().post("/exam/test/", {
            "subsection_name": "repeat_sentence",
            "question_text": "Students must submit the assignment before Friday",
            "audio_text": "Purple elephants dance beneath silver clouds",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["evaluation"]["scores"]["content"]["score"], 0)

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_diagnostic_endpoint_accepts_question_image(self, evaluate):
        self.subsection("describe_image")
        evaluate.return_value = provider_result()
        response = APIClient().post("/exam/test/", {
            "subsection_name": "describe_image", "question_text": "Describe this chart",
            "audio_text": "The chart shows rising sales.", "question_image": image_url(),
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(evaluate.call_args.kwargs["image_data_url"], image_url())

    def test_publication_audit_requires_lecture_and_discussion_references(self):
        for name in ("retell_lecture", "summarise_group_discussion", "summarize_spoken_text"):
            question = Question.objects.create(subsection=self.subsection(name), name="Source task", text="Summarize the audio", speaking_score_max=3)
            auditor = QuestionBankAuditor(check_storage=False, include_response_context=False)
            codes = {issue["code"] for issue in auditor.question_issues(question)}
            self.assertIn("missing_ai_reference", codes)
            question.correct_answer = "Reviewed source key points"
            codes = {issue["code"] for issue in auditor.question_issues(question)}
            self.assertNotIn("missing_ai_reference", codes)

    def test_trainer_publication_message_explains_where_to_add_source(self):
        message = MockTestAdminForm._format_publication_error({"code": "missing_ai_reference"})
        self.assertIn("Correct answer", message)
        self.assertIn("original content", message)

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_language_repair_can_correct_grammar_without_changing_content(self, evaluate):
        subsection = self.subsection("write_essay")
        subsection.rubric = {"content": {"max": 3}, "grammar": {"max": 2}}
        subsection.save(update_fields=["rubric"])
        outputs = []
        for content, grammar in ((2, 2), (1, 2), (0, 1)):
            outputs.append({
                "success": True,
                "data": {
                    "scores": {
                        "content": {"score": content, "max": 3},
                        "grammar": {"score": grammar, "max": 2},
                    },
                    "feedback": {"errors": [{
                        "type": "grammar", "text": "This are", "suggestion": "This is",
                    }]},
                },
            })
        evaluate.side_effect = outputs

        result = run_evaluation_for_subsection(subsection, "Write about the topic", {
            "answer_data": "This are wrong.",
        })

        self.assertTrue(result["ok"], result)
        self.assertEqual(evaluate.call_count, 3)
        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 2)
        self.assertEqual(result["evaluation"]["scores"]["grammar"]["score"], 1)
        self.assertEqual(result["evaluation"]["weighted_score"], 3)


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}})
class QuestionTaskImageContextTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Speaking")
        self.subsection = SubSection.objects.create(
            section=section, name="describe_image", evaluation_type="ai", ai_input_type="audio",
            rubric={"content": {"max": 3}}, trait_skill_map={"content": ["speaking"]},
        )
        self.paper = MockTest.objects.create(title="Image evaluation QA", scoring_mode="v2")
        self.paper_section = MockTestSection.objects.create(mock_test=self.paper, section=section, order=1)

    def response(self, kind, *, with_image=False):
        question = Question.objects.create(
            subsection=self.subsection, mock_test_section=self.paper_section,
            text="Describe the chart", speaking_score_max=3,
            image=SimpleUploadedFile("chart.png", image_data()) if with_image else None,
        )
        common = {"question": question, "transcribed_audio_data": {"transcription": {"text": "The chart shows rising sales."}}}
        if kind == "single":
            return SingleResponse.objects.create(name="QA candidate", scoring_mode="v2", **common), evaluate_single_response
        session = UserMockTestSession.objects.create(
            name="QA candidate", session_id="source-context-test", mock_test=self.paper, scoring_mode="v2",
        )
        return UserResponse.objects.create(user_session=session, mock_test=self.paper, **common), evaluate_user_response

    @patch("mocktest.tasks.run_evaluation_for_subsection")
    def test_both_response_tasks_forward_the_stored_question_image(self, evaluate):
        evaluate.return_value = {"ok": True, "evaluation": provider_result()["data"]}
        for kind in ("single", "user"):
            with self.subTest(kind=kind):
                response, task = self.response(kind, with_image=True)
                result = task.apply(args=(response.pk, response.question_id))
                self.assertTrue(result.successful(), result.result)
                self.assertEqual(evaluate.call_args.args[2]["question_image"]["data_url"], image_url())
                self.assertIn("The chart shows rising sales.", str(evaluate.call_args.args[2]))

    @patch("mocktest.tasks.run_evaluation_for_subsection")
    def test_missing_question_image_fails_both_tasks_without_ai(self, evaluate):
        for kind in ("single", "user"):
            with self.subTest(kind=kind):
                response, task = self.response(kind)
                result = task.apply(args=(response.pk, response.question_id))
                response.refresh_from_db()
                self.assertTrue(result.failed())
                self.assertFalse(response.evaluated)
                self.assertEqual(response.evaluation_result["code"], "missing_question_image")
                self.assertFalse(response.evaluation_result["retryable"])
        evaluate.assert_not_called()
