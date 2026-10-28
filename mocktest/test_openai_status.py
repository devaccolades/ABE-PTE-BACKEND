from datetime import timedelta
from unittest.mock import patch

import httpx
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from openai import RateLimitError

from examinor.services.evaluator import evaluate_with_openai
from examinor.services.openai_errors import (
    CREDITS_EXHAUSTED_ERROR, RATE_LIMIT_ERROR, format_openai_error, is_credits_exhausted,
)
from mocktest.models import (
    MockTest, MockTestSection, Question, Section, SingleResponse, SubSection,
    UserMockTestSession, UserResponse,
)
from mocktest.services.openai_status import openai_status
from mocktest.tasks import evaluation_retry_allowed


def rate_limit_error(code, error_type):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    # Shape returned by OpenAI: the client unwraps the "error" object into body.
    return RateLimitError(
        "Error code: 429", response=httpx.Response(429, request=request),
        body={"message": "429", "type": error_type, "code": code, "param": None},
    )


NO_CREDITS = ("credit_balance_exhausted", "insufficient_quota")
TOO_FAST = ("rate_limit_exceeded", "requests")


class OpenAIErrorClassificationTests(SimpleTestCase):
    def test_empty_account_is_reported_as_credits_not_rate_limit(self):
        error = rate_limit_error(*NO_CREDITS)
        self.assertTrue(is_credits_exhausted(error))
        self.assertEqual(format_openai_error(error), CREDITS_EXHAUSTED_ERROR)

    def test_real_rate_limit_keeps_its_message(self):
        error = rate_limit_error(*TOO_FAST)
        self.assertFalse(is_credits_exhausted(error))
        self.assertEqual(format_openai_error(error), RATE_LIMIT_ERROR)

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("examinor.services.evaluator.get_openai_client")
    def test_exhausted_credits_are_not_retried_but_rate_limits_are(self, get_client):
        get_client.return_value.responses.create.side_effect = rate_limit_error(*NO_CREDITS)
        result = evaluate_with_openai("prompt", "hash")
        self.assertEqual(result["error"], CREDITS_EXHAUSTED_ERROR)
        self.assertFalse(evaluation_retry_allowed(result, current_retries=0))

        get_client.return_value.responses.create.side_effect = rate_limit_error(*TOO_FAST)
        result = evaluate_with_openai("prompt", "hash")
        self.assertTrue(evaluation_retry_allowed(result, current_retries=0))


class OpenAIStatusTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Writing")
        subsection = SubSection.objects.create(section=section, name="write_essay", rubric={"content": {"max": 6}})
        mock_test = MockTest.objects.create(title="Status")
        self.question = Question.objects.create(
            mock_test_section=MockTestSection.objects.create(mock_test=mock_test, section=section),
            subsection=subsection, text="Essay prompt",
        )
        self.mock_test = mock_test
        self.now = timezone.now()

    def response(self, status, error="", minutes_ago=0, single=False):
        fields = {
            "question": self.question, "evaluation_status": status, "evaluation_error": error,
            "last_evaluation_attempt_at": self.now - timedelta(minutes=minutes_ago),
        }
        if single:
            return SingleResponse.objects.create(**fields)
        # One response per session and question, so each needs its own session.
        session = UserMockTestSession.objects.create(
            name="Student", session_id=f"status-{UserMockTestSession.objects.count()}", mock_test=self.mock_test,
        )
        return UserResponse.objects.create(user_session=session, mock_test=self.mock_test, **fields)

    def test_no_failures_is_working(self):
        self.response("completed")
        status = openai_status()
        self.assertEqual((status["state"], status["affected"]), ("working", 0))

    def test_credit_failures_after_the_last_success_are_current(self):
        self.response("completed", minutes_ago=30)
        self.response("failed", CREDITS_EXHAUSTED_ERROR, minutes_ago=5)
        self.response("failed", CREDITS_EXHAUSTED_ERROR, minutes_ago=1, single=True)
        status = openai_status()
        self.assertEqual(status["state"], "credits_exhausted")
        self.assertEqual(status["affected"], 2)
        self.assertEqual(status["since"], self.now - timedelta(minutes=1))

    def test_errors_stored_before_this_change_still_raise_an_alert(self):
        self.response("failed", "OpenAI API rate limit exceeded", minutes_ago=1)
        self.assertEqual(openai_status()["state"], "rate_limited")

    def test_recovery_reports_failures_that_need_a_retry(self):
        self.response("failed", CREDITS_EXHAUSTED_ERROR, minutes_ago=10)
        self.response("completed", minutes_ago=1)
        status = openai_status()
        self.assertEqual(status["state"], "working")
        self.assertEqual(status["affected"], 1)
        self.assertIn("need a retry", status["detail"])

    def test_raw_quota_text_is_counted_once(self):
        self.response("failed", "429 insufficient_quota: You have no credits remaining", minutes_ago=1)
        status = openai_status()
        self.assertEqual((status["state"], status["affected"]), ("credits_exhausted", 1))

    def test_unrelated_failures_do_not_raise_an_alert(self):
        self.response("failed", "Evaluation output failed validation: bad score", minutes_ago=1)
        self.assertEqual(openai_status()["affected"], 0)


class OpenAIStatusAdminTests(OpenAIStatusTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(User.objects.create_superuser("admin", "admin@example.com", "password"))

    def test_dashboard_shows_the_credit_alert_with_billing_link(self):
        self.response("failed", CREDITS_EXHAUSTED_ERROR, minutes_ago=1)
        page = self.client.get("/admin/")
        self.assertContains(page, "OpenAI credits exhausted")
        self.assertContains(page, "platform.openai.com/settings/organization/billing")

    def test_dashboard_shows_working_when_healthy(self):
        self.response("completed")
        self.assertContains(self.client.get("/admin/"), "OpenAI working")

    def test_response_lists_show_the_credit_banner(self):
        self.response("failed", CREDITS_EXHAUSTED_ERROR, minutes_ago=1)
        for url in ("/admin/mocktest/userresponse/", "/admin/mocktest/singleresponse/"):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), "OpenAI credits exhausted")
