from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from examinor.models import EvaluationCache
from examinor.scoring.response_scores import compile_response_score_evidence
from examinor.services.orchestrator import run_evaluation_for_subsection
from examinor.services.strict_form import apply_strict_form_override, apply_strict_form_policy, inspect_strict_form
from mocktest.models import (
    MockTest, MockTestSection, Question, Section, SingleResponse, SubSection,
    UserMockTestSession, UserResponse,
)
from mocktest.tasks import evaluate_single_response, evaluate_user_response, validate_evaluation_or_fail


def answer_with_words(count):
    return " ".join(f"word{index}" for index in range(count)) + "."


def evaluation(form_score=2, form_maximum=2):
    return {"scores": {
        "content": {"score": 4, "max": 6},
        "form": {"score": form_score, "max": form_maximum},
    }, "weighted_score": 4 + form_score, "feedback": {"summary": "Rubric feedback", "errors": []}}


@override_settings(STRICT_FORM_POLICY_ENABLED=True)
class StrictFormTests(SimpleTestCase):
    def test_exact_inclusive_company_word_limits(self):
        for task, minimum, maximum in (
            ("summarize_spoken_text", 50, 70),
            ("summarize_written_text", 5, 75),
            ("write_essay", 200, 300),
        ):
            for count in (minimum - 1, minimum, maximum, maximum + 1):
                with self.subTest(task=task, count=count):
                    result = inspect_strict_form(answer_with_words(count), task)
                    self.assertEqual(result["word_count"], count)
                    self.assertEqual(result["is_invalid"], not minimum <= count <= maximum)
                    self.assertEqual(result["policy_source"], "company")

    def test_pearson_partial_word_ranges_are_zero_under_company_policy(self):
        for task, counts in (
            ("summarize_spoken_text", (40, 49, 71, 100)),
            ("write_essay", (120, 199, 301, 380)),
        ):
            for count in counts:
                with self.subTest(task=task, count=count):
                    self.assertTrue(inspect_strict_form(answer_with_words(count), task)["is_invalid"])

    def test_swt_multiple_sentences_fail_but_abbreviations_and_decimals_do_not(self):
        result = inspect_strict_form("The report shows growth. Costs also decreased.", "summarize_written_text")
        self.assertTrue(result["is_invalid"])
        self.assertEqual(result["sentence_count"], 2)
        result = inspect_strict_form("Dr. Smith reported a 3.5 percent rise, which indicates steady growth.", "summarize_written_text")
        self.assertFalse(result["is_invalid"])
        self.assertEqual(result["sentence_count"], 1)

    def test_semicolon_connected_summary_remains_one_sentence(self):
        self.assertFalse(inspect_strict_form(
            "Sales increased steadily; however, staffing costs remained unchanged.", "summarize_written_text",
        )["is_invalid"])

    def test_empty_and_punctuation_only_answers_fail(self):
        for text in ("", "   ", ". , ! ..."):
            self.assertTrue(inspect_strict_form(text, "write_essay")["is_invalid"])

    def test_word_count_handles_unicode_spaces_hyphens_and_contractions(self):
        result = inspect_strict_form("We\u00a0can't ignore state-of-the-art systems.", "summarize_written_text")
        self.assertEqual(result["word_count"], 5)
        self.assertFalse(result["is_invalid"])

    def test_partial_assessed_form_zeroes_every_skill_in_all_modes(self):
        text = answer_with_words(60)
        result = {"ok": True, "evaluation": evaluation(form_score=1)}
        result = apply_strict_form_override(result, inspect_strict_form(text, "summarize_spoken_text", result["evaluation"]))
        self.assertEqual(result["score_overrides"][0]["original_weighted_score"], 5)
        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        self.assertIn("company strict Form", result["evaluation"]["feedback"]["summary"])
        question = SimpleNamespace(
            subsection=SimpleNamespace(name="summarize_spoken_text", trait_skill_map={"content": ["writing", "listening"], "form": ["writing"]}),
            speaking_score_max=0, reading_score_max=0, writing_score_max=8, listening_score_max=6,
        )
        for mode in ("legacy", "shadow", "v2"):
            evidence = compile_response_score_evidence(question, result, mode=mode)
            self.assertTrue(all(item["score"] == 0 for item in evidence["promoted"]["skills"].values()))

    def test_other_task_types_are_unaffected(self):
        for task in ("read_aloud", "repeat_sentence", "respond_to_a_situation", "describe_image", "mc_multiple", "write_from_dictation"):
            self.assertFalse(inspect_strict_form("Short answer", task)["applicable"])

    def test_another_gate_zero_does_not_create_a_false_form_failure(self):
        result = {"ok": True, "evaluation": evaluation(form_score=0), "score_overrides": [{
            "code": "template_content_dominated", "original_scores": evaluation()["scores"],
        }]}
        result = apply_strict_form_policy(result, "write_essay", answer_with_words(200))
        self.assertFalse(result["integrity_checks"]["strict_form"]["is_invalid"])
        self.assertEqual(len(result["score_overrides"]), 1)

    @override_settings(STRICT_FORM_POLICY_ENABLED=False)
    def test_emergency_switch_disables_only_this_policy(self):
        self.assertFalse(inspect_strict_form("Short answer", "write_essay")["applicable"])


@override_settings(
    STRICT_FORM_POLICY_ENABLED=True, TEMPLATE_CONTENT_CONFIG={"enabled": False},
    REPETITIVE_ANSWER_CONFIG={"enabled": False}, KNOWN_TEMPLATE_CONFIG={"enabled": False},
)
class StrictFormIntegrationTests(TestCase):
    def setUp(self):
        self.section = Section.objects.create(name="Writing")

    def subsection(self, task):
        maximum = 1 if task == "summarize_written_text" else 2
        return SubSection.objects.create(
            section=self.section, name=task, evaluation_type="ai", ai_input_type="text",
            rubric={"content": {"max": 6}, "form": {"max": maximum}},
            trait_skill_map={"content": ["writing"], "form": ["writing"]},
        )

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_invalid_lengths_stop_before_ai_or_cache(self, evaluate):
        for task, count in (("write_essay", 199), ("summarize_spoken_text", 71), ("summarize_written_text", 76)):
            result = run_evaluation_for_subsection(self.subsection(task), "Actual task prompt", {
                "answer_data": answer_with_words(count), "reference_answer": "Reviewed source material",
            })
            self.assertTrue(result["ok"])
            self.assertFalse(result["provider_called"])
            self.assertEqual(result["evaluation"]["weighted_score"], 0)
            self.assertEqual(result["score_overrides"][0]["code"], "company_strict_form")
        evaluate.assert_not_called()
        self.assertFalse(EvaluationCache.objects.exists())

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_in_range_answer_is_still_normally_evaluated(self, evaluate):
        evaluate.return_value = {"success": True, "data": evaluation()}
        result = run_evaluation_for_subsection(self.subsection("write_essay"), "Actual essay question", {"answer_data": answer_with_words(200)})
        self.assertTrue(result["ok"])
        self.assertEqual(result["evaluation"]["weighted_score"], 6)
        self.assertFalse(result["integrity_checks"]["strict_form"]["is_invalid"])
        evaluate.assert_called_once()

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_partial_form_cached_result_cannot_bypass_policy(self, evaluate):
        evaluate.return_value = {"success": True, "data": evaluation()}
        subsection = self.subsection("write_essay")
        payload = {"answer_data": answer_with_words(200)}
        first = run_evaluation_for_subsection(subsection, "Actual essay question", payload)
        self.assertEqual(first["evaluation"]["weighted_score"], 6)
        cached = EvaluationCache.objects.get()
        cached.result = evaluation(form_score=1)
        cached.save(update_fields=["result"])
        second = run_evaluation_for_subsection(subsection, "Actual essay question", payload)
        self.assertTrue(second["cached"])
        self.assertEqual(second["evaluation"]["weighted_score"], 0)
        self.assertEqual(evaluate.call_count, 1)

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_full_and_single_exam_answers_persist_zero_with_reason(self, evaluate):
        for task, count in (("write_essay", 199), ("summarize_spoken_text", 71), ("summarize_written_text", 76)):
            subsection = self.subsection(task)
            paper = MockTest.objects.create(title=task, scoring_mode="v2")
            paper_section = MockTestSection.objects.create(mock_test=paper, section=self.section, order=1)
            question = Question.objects.create(
                name=task, text="Actual task question", correct_answer="Reviewed source material",
                subsection=subsection, mock_test_section=paper_section, writing_score_max=8,
            )
            session = UserMockTestSession.objects.create(mock_test=paper, name="QA", session_id=task, scoring_mode="v2")
            common = {"question": question, "answer_data": answer_with_words(count)}
            rows = (
                (SingleResponse.objects.create(name="QA", scoring_mode="v2", **common), evaluate_single_response),
                (UserResponse.objects.create(mock_test=paper, user_session=session, **common), evaluate_user_response),
            )
            for response, task_function in rows:
                with self.subTest(task=task, model=type(response).__name__):
                    execution = task_function.apply(args=(response.pk, question.pk))
                    self.assertTrue(execution.successful(), execution.result)
                    response.refresh_from_db()
                    self.assertTrue(response.evaluated)
                    self.assertEqual(response.writing_score_awarded, 0)
                    self.assertTrue(response.evaluation_result["integrity_checks"]["strict_form"]["is_invalid"])
                    self.assertIn("Company policy", response.evaluation_result["evaluation"]["feedback"]["summary"])
        evaluate.assert_not_called()

    def test_final_validation_also_catches_direct_positive_provider_results(self):
        subsection = self.subsection("write_essay")
        response = SimpleNamespace(
            answer_data=answer_with_words(199), transcribed_audio_data=None,
            question=SimpleNamespace(text="Actual essay topic"),
        )
        result = validate_evaluation_or_fail(response, {"ok": True, "evaluation": evaluation()}, subsection)
        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        self.assertEqual(result["score_overrides"][0]["original_weighted_score"], 6)


@override_settings(STRICT_FORM_POLICY_ENABLED=True)
class CapitalsAndBulletFormTests(SimpleTestCase):
    SUMMARY = (
        "The lecture explained that emotional stability differs between people, and while some "
        "enjoy intense experiences, the speaker argued that a calm and stable mood matters more "
        "for lasting happiness, so moderation and balance between excitement and contentment are "
        "the real secret of a good life for most people."
    )

    def violations(self, answer, task="summarize_spoken_text"):
        return inspect_strict_form(answer, task)["violations"]

    def test_answers_in_capital_letters_get_form_zero_for_every_task(self):
        for task in ("summarize_written_text", "summarize_spoken_text", "write_essay"):
            with self.subTest(task=task):
                result = inspect_strict_form(self.SUMMARY.upper(), task)
                self.assertTrue(result["is_invalid"])
                self.assertIn("written_in_capitals", result["violations"])
                self.assertIn("capital letters", result["reason"])

    def test_names_acronyms_and_a_capitalised_heading_are_not_all_capitals(self):
        answer = "NASA, the UN and the WHO agree. " + self.SUMMARY
        self.assertNotIn("written_in_capitals", self.violations(answer))
        self.assertNotIn("written_in_capitals", self.violations("SUMMARY: " + self.SUMMARY))

    def test_answers_made_only_of_bullet_points_get_form_zero(self):
        for marker in ("-", "*", "•", "1.", "2)"):
            answer = "\n".join(f"{marker} {line}" for line in self.SUMMARY.split(", "))
            with self.subTest(marker=marker):
                self.assertIn("only_bullet_points", self.violations(answer))

    def test_prose_with_a_list_or_hyphenated_words_is_not_only_bullet_points(self):
        mixed = self.SUMMARY + "\n- moderation\n- balance"
        self.assertNotIn("only_bullet_points", self.violations(mixed))
        self.assertNotIn("only_bullet_points", self.violations("- " + self.SUMMARY))
        self.assertNotIn("only_bullet_points", self.violations(self.SUMMARY.replace("calm", "well-balanced")))
