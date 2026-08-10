from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from mocktest.models import (
    EvaluationAttempt,
    EvaluationJob,
    EvaluationOutbox,
    MockTest,
    MockTestSection,
    Question,
    Section,
    SubSection,
    UserMockTestSession,
    UserResponse,
)
from mocktest.services.evaluation_jobs import (
    dispatch_pending_outbox_events,
    finish_evaluation_attempt,
    prepare_evaluation_dispatch,
    start_evaluation_attempt,
)
from mocktest.services.evaluation_queue import (
    EvaluationQueueUnavailable,
    queue_response_evaluation,
)
from mocktest.tasks import evaluate_user_response


@override_settings(
    EVALUATION_ENGINE_VERSION="test-engine-v1",
    EVALUATION_JOB_LEASE_SECONDS=60,
    EVALUATION_OUTBOX_RETRY_BASE_SECONDS=0,
    EVALUATION_OUTBOX_RETRY_MAX_SECONDS=0,
)
class EvaluationJobTests(TestCase):
    def setUp(self):
        mock_test = MockTest.objects.create(title="Durable evaluation test")
        section = Section.objects.create(name="Writing")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="write_essay",
            order=1,
        )
        self.question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="WE-DURABLE",
            text="Write an essay.",
        )
        self.session = UserMockTestSession.objects.create(
            name="Student",
            session_id="durable-evaluation-session",
            mock_test=mock_test,
        )
        self.response = UserResponse.objects.create(
            user_session=self.session,
            mock_test=mock_test,
            question=self.question,
            answer_data={"text": "A valid answer."},
        )

    @patch("mocktest.tasks.evaluate_user_response.delay")
    def test_queue_persists_job_before_successful_publish(self, mock_delay):
        mode = queue_response_evaluation(self.response)

        self.assertEqual(mode, "evaluation")
        job = EvaluationJob.objects.get()
        event = EvaluationOutbox.objects.get()
        self.assertEqual(job.status, "dispatched")
        self.assertEqual(job.response_type, "user")
        self.assertEqual(job.response_id, self.response.pk)
        self.assertEqual(job.engine_version, "test-engine-v1")
        self.assertIsNotNone(event.published_at)
        self.assertEqual(event.publish_attempts, 1)
        mock_delay.assert_called_once_with(self.response.pk, self.question.pk)

    @patch("mocktest.tasks.evaluate_user_response.delay")
    def test_repeated_queue_request_does_not_publish_twice(self, mock_delay):
        first_mode = queue_response_evaluation(self.response)
        second_mode = queue_response_evaluation(self.response)

        self.assertEqual(first_mode, "evaluation")
        self.assertEqual(second_mode, "already_processing")
        self.assertEqual(EvaluationJob.objects.count(), 1)
        self.assertEqual(EvaluationOutbox.objects.count(), 1)
        mock_delay.assert_called_once_with(self.response.pk, self.question.pk)

    @patch(
        "mocktest.tasks.evaluate_user_response.delay",
        side_effect=ConnectionError("Redis unavailable"),
    )
    def test_publish_failure_remains_durable_and_pending(self, mock_delay):
        with self.assertRaises(EvaluationQueueUnavailable):
            queue_response_evaluation(self.response)

        self.response.refresh_from_db()
        job = EvaluationJob.objects.get()
        event = EvaluationOutbox.objects.get()
        self.assertEqual(self.response.evaluation_status, "pending")
        self.assertEqual(self.response.evaluation_stage, "queueing")
        self.assertEqual(job.status, "waiting_dispatch")
        self.assertIsNone(event.published_at)
        self.assertEqual(event.publish_attempts, 1)
        self.assertIn("Redis unavailable", event.last_error)

    def test_unpublished_event_is_recovered_without_duplicate_job(self):
        with patch(
            "mocktest.tasks.evaluate_user_response.delay",
            side_effect=ConnectionError("Redis unavailable"),
        ):
            with self.assertRaises(EvaluationQueueUnavailable):
                queue_response_evaluation(self.response)

        with patch("mocktest.tasks.evaluate_user_response.delay") as mock_delay:
            result = dispatch_pending_outbox_events()

        self.assertEqual(
            result,
            {"processed": 1, "published": 1, "failed": 0, "already_claimed": 0},
        )
        self.assertEqual(EvaluationJob.objects.count(), 1)
        self.assertEqual(EvaluationOutbox.objects.count(), 1)
        event = EvaluationOutbox.objects.get()
        self.assertIsNotNone(event.published_at)
        self.assertEqual(event.publish_attempts, 2)
        mock_delay.assert_called_once_with(self.response.pk, self.question.pk)

    def test_repeated_failed_queue_request_reuses_unpublished_event(self):
        with patch(
            "mocktest.tasks.evaluate_user_response.delay",
            side_effect=ConnectionError("Redis unavailable"),
        ):
            for _ in range(2):
                with self.assertRaises(EvaluationQueueUnavailable):
                    queue_response_evaluation(self.response)

        self.assertEqual(EvaluationJob.objects.count(), 1)
        self.assertEqual(EvaluationOutbox.objects.count(), 1)
        self.assertEqual(EvaluationOutbox.objects.get().publish_attempts, 2)

    def test_changed_input_creates_a_new_idempotency_job(self):
        prepare_evaluation_dispatch(self.response)
        self.response.answer_data = {"text": "A revised answer."}
        self.response.save(update_fields=["answer_data"])

        prepare_evaluation_dispatch(self.response)

        self.assertEqual(EvaluationJob.objects.count(), 2)
        self.assertEqual(
            EvaluationJob.objects.values("input_hash").distinct().count(),
            2,
        )

    def test_active_job_lease_rejects_duplicate_worker_claim(self):
        job, _ = prepare_evaluation_dispatch(self.response)

        first = start_evaluation_attempt(
            self.response,
            "evaluation",
            task_id="task-1",
        )
        second = start_evaluation_attempt(
            self.response,
            "evaluation",
            task_id="task-2",
        )

        self.assertEqual(first, "claimed")
        self.assertEqual(second, "busy")
        job.refresh_from_db()
        self.assertEqual(job.status, "processing")
        self.assertEqual(job.current_attempt, 1)
        self.assertEqual(EvaluationAttempt.objects.count(), 1)

    @override_settings(EVALUATION_OUTBOX_STALE_SECONDS=300)
    def test_runtime_check_rejects_stale_unpublished_outbox_work(self):
        prepare_evaluation_dispatch(self.response)
        EvaluationOutbox.objects.update(
            created_at=timezone.now() - timezone.timedelta(seconds=301)
        )

        with self.assertRaises(CommandError):
            call_command(
                "check_evaluation_runtime",
                "--skip-redis",
                "--skip-celery",
                stdout=StringIO(),
            )

    def test_finishing_attempt_promotes_job_once(self):
        job, _ = prepare_evaluation_dispatch(self.response)
        start_evaluation_attempt(self.response, "evaluation", task_id="task-1")

        finish_evaluation_attempt(
            self.response,
            succeeded=True,
            result={"ok": True},
        )

        job.refresh_from_db()
        attempt = EvaluationAttempt.objects.get()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.lease_owner, "")
        self.assertIsNone(job.lease_expires_at)
        self.assertIsNotNone(attempt.finished_at)
        self.assertEqual(attempt.normalized_result, {"ok": True})

    def test_worker_completion_closes_job_and_attempt(self):
        self.response.answer_data = {}
        self.response.save(update_fields=["answer_data"])
        job, _ = prepare_evaluation_dispatch(self.response)

        result = evaluate_user_response.apply(
            args=(self.response.pk, self.question.pk),
        )

        self.assertFalse(result.failed())
        self.response.refresh_from_db()
        job.refresh_from_db()
        attempt = EvaluationAttempt.objects.get(job=job)
        self.assertTrue(self.response.evaluated)
        self.assertEqual(self.response.evaluation_status, "completed")
        self.assertEqual(job.status, "completed")
        self.assertIsNotNone(attempt.finished_at)

    @patch("mocktest.tasks.run_evaluation_for_subsection")
    def test_duplicate_delivery_returns_completed_result_without_provider_call(
        self,
        mock_provider,
    ):
        job, _ = prepare_evaluation_dispatch(self.response)
        self.response.evaluated = True
        self.response.evaluation_status = "completed"
        self.response.save(update_fields=["evaluated", "evaluation_status"])
        job.status = "processing"
        job.lease_owner = "dead-worker"
        job.lease_expires_at = timezone.now() - timezone.timedelta(seconds=1)
        job.save(
            update_fields=[
                "status",
                "lease_owner",
                "lease_expires_at",
                "updated_at",
            ]
        )

        result = evaluate_user_response.apply(
            args=(self.response.pk, self.question.pk),
        )

        self.assertFalse(result.failed())
        self.assertEqual(result.result["status"], "already_completed")
        mock_provider.assert_not_called()
        self.assertEqual(EvaluationAttempt.objects.count(), 0)
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.lease_owner, "")
