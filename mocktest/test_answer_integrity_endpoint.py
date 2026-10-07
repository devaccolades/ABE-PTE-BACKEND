from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from mocktest.models import AnswerTemplate


class AnswerIntegrityTestEndpointTests(TestCase):
    def setUp(self):
        self.url = reverse("answer-integrity-test")
        self.staff = get_user_model().objects.create_user(
            username="integrity-reviewer",
            password="test-password",
            is_staff=True,
        )

    def _post(self, payload):
        self.client.force_login(self.staff)
        return self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
        )

    def test_staff_user_can_list_supported_answer_types(self):
        self.client.force_login(self.staff)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "describe_image",
            response.json()["supported_answer_types"],
        )
        self.assertNotIn(
            "mc_single",
            response.json()["supported_answer_types"],
        )

    def test_staff_user_can_test_normal_answer(self):
        response = self._post({
            "answer_type": "describe_image",
            "text": (
                "The photograph shows a railway platform during the morning. "
                "Several passengers wait beside a digital timetable while an "
                "employee helps a traveller near the ticket desk. Sunlight "
                "enters through the glass roof, and the station appears busy "
                "but orderly."
            ),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["decision"], "pass")
        self.assertTrue(payload["passes"])
        self.assertFalse(payload["would_score_zero"])
        self.assertEqual(payload["blocked_by"], [])
        self.assertIn("repetition", payload["checks"])
        self.assertIn("known_template", payload["checks"])

    def test_repetitive_answer_reports_blocking_condition(self):
        sentence = (
            "The picture clearly presents the same prepared description for "
            "every visible feature."
        )
        response = self._post({
            "answer_type": "describe_image",
            "text": " ".join([sentence] * 8),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["decision"], "blocked")
        self.assertIn("repetition", payload["blocked_by"])
        self.assertTrue(payload["checks"]["repetition"]["blocked"])
        self.assertIn(
            "repeated",
            payload["checks"]["repetition"]["reason"].lower(),
        )
        evidence = payload["checks"]["repetition"]["evidence"]
        self.assertTrue(evidence["conditions"]["minimum_length_met"])
        self.assertIn("hard_repetition_ratio", evidence["thresholds"])

    def test_known_template_answer_reports_match_evidence(self):
        template = AnswerTemplate.objects.create(
            name="Endpoint template",
            answer_type="describe_image",
            template_text=(
                "The supplied image provides information about [[topic]]. "
                "The main feature can be observed clearly in the centre. "
                "The remaining details support this general observation. "
                "Overall the image is informative and useful for reference."
            ),
            minimum_match_ratio=0.55,
            maximum_original_words=10,
            minimum_matched_words=20,
            minimum_match_blocks=2,
        )
        response = self._post({
            "answer_type": "describe_image",
            "text": (
                "The supplied image provides information about employment. "
                "The main feature can be observed clearly in the centre. "
                "The remaining details support this general observation. "
                "Overall the image is informative and useful for reference."
            ),
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("known_template", payload["blocked_by"])
        evidence = payload["checks"]["known_template"]["evidence"]
        self.assertEqual(evidence["matched_template"]["id"], template.pk)
        self.assertGreater(evidence["answer_match_ratio"], 0.55)
        self.assertIn("thresholds", evidence)

    def test_objective_answer_type_is_rejected(self):
        response = self._post({
            "answer_type": "mc_single",
            "text": "A random answer",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("answer_type", response.json())

    def test_non_staff_user_cannot_probe_integrity_rules(self):
        response = self.client.post(
            self.url,
            data={
                "answer_type": "describe_image",
                "text": "A random description for testing.",
            },
            content_type="application/json",
        )

        self.assertIn(response.status_code, {401, 403})
