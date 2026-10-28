from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.core.management import call_command

from examinor.models import EvaluationCache
from examinor.scoring.response_scores import compile_response_score_evidence
from examinor.services.orchestrator import run_evaluation_for_subsection
from examinor.services.source_fidelity import (
    audit_source_fidelity, build_fidelity_prompt, quote_matches, validate_fidelity_assessment,
)
from mocktest.models import (
    MockTest, MockTestSection, Question, Section, SingleResponse, SubSection,
    UserMockTestSession, UserResponse,
)
from mocktest.tasks import evaluate_single_response, evaluate_user_response


SOURCE = (
    "Three students discuss mandatory physical education. The first opposes it "
    "because it is stressful and unfair. The second supports exercise for health "
    "and better concentration. The third suggests inclusive yoga and walking clubs. "
    "They agree that flexible activities would improve the courses."
)
PETS = (
    "In this discussion, three students were basically talking about the pet animals "
    "they just keep in their house. The first student said they own an elephant "
    "and that elephant is black in color, it has some big ears and it is very "
    "talkative and it always communicates to the favorite food. The second student "
    "then talked about a pet animal of his which is a dog and that dog is a corgi "
    "and surprisingly the corgi was a vegetarian. The corgi doesn't speak, it barks "
    "and it behaves like a normal dog and he said it loves a lot of attention. "
    "And the corgi was also three years old. The third student then went on "
    "discussing about her pets. She actually said she kept a butterfly at her home "
    "and they actually built a garden for that particular butterfly. And she also "
    "said an amazing fact that the butterfly is 40 years old. Along with the "
    "butterfly, there is also a black color snake in their garden and that snake "
    "is very friendly even if it is poisonous. She also said that next to that "
    "particular garden, they have built a big river for some exotic animals and "
    "exotic fishes to live. So she actually keeps, so all the other students said, "
    "the third student is actually keeping a particular jungle in her home rather "
    "than keeping pet animals. Anyways all of them were laughing at the characters "
    "and features of the animals or the pet animals they keep in their home and "
    "they went back to home after seeing all these details."
)
FAITHFUL = (
    "Students disagree about compulsory sport lessons. One finds them stressful, "
    "whereas another values the health and focus benefits. Their compromise is "
    "a more inclusive choice of activities, including walking and yoga, to accommodate "
    "people with differing abilities and interests."
)
CLIMATE_SOURCE = "Climate change threatens indigenous food supplies and cultural heritage."
REVERSED = (
    "Climate change does not threaten indigenous food supplies or cultural heritage; "
    "it has little impact on their communities, so their participation in environmental "
    "policy is unnecessary and the global community need not consider their experiences."
)


def audit(verdict="off_topic", answer=PETS, source=SOURCE, confidence=0.99):
    relation = {"grounded": "supported", "mixed": "supported",
                "contradictory": "contradicted"}.get(verdict, "unrelated")
    return {
        "verdict": verdict, "confidence": confidence,
        "reason": "The response discusses pets instead of compulsory physical education.",
        "evidence": [{"candidate_quote": answer, "source_quote": source,
                      "relation": relation, "reason": "Compare the claims and main topic."}],
    }


def graded(answer=PETS):
    return {
        "scores": {"content": {"score": 5, "max": 6},
                   "oral_fluency": {"score": 4, "max": 5},
                   "pronunciation": {"score": 1, "max": 5}},
        "feedback": "The response captures the main ideas.",
        "template_assessment": {
            "verdict": "substantive", "confidence": 0.99, "addresses_task": True,
            "generic_passages": [],
            "specific_points": [{"text": answer, "reason": "The grader claims this is relevant."}],
            "reason": "Initial grader thinks the response addresses the task.",
        },
    }


class SourceFidelityValidationTests(SimpleTestCase):
    def test_exact_but_semantically_different_evidence_is_permitted_for_review(self):
        self.assertEqual(validate_fidelity_assessment(audit(), PETS, SOURCE), (True, None))

    def test_reversed_claims_have_explicit_contradiction_evidence(self):
        data = audit("contradictory", REVERSED, CLIMATE_SOURCE)
        self.assertTrue(validate_fidelity_assessment(data, REVERSED, CLIMATE_SOURCE)[0])

    def test_fabricated_quotes_invalid_types_and_inconsistent_verdicts_are_rejected(self):
        variants = [None, {}, {**audit(), "confidence": float("nan")},
                    {**audit(), "confidence": True}, {**audit(), "reason": ""},
                    {**audit(), "evidence": []}]
        for field, value in (("candidate_quote", "invented words"),
                             ("source_quote", "fabricated source"),
                             ("relation", "unsupported"), ("reason", "")):
            data = audit()
            data["evidence"][0][field] = value
            variants.append(data)
        variants.append({**audit(), "verdict": "grounded"})
        data = audit()
        data["evidence"].append(audit("grounded")["evidence"][0])
        variants.append(data)
        for data in variants:
            with self.subTest(data=data):
                self.assertFalse(validate_fidelity_assessment(data, PETS, SOURCE)[0])

    def test_quotes_tolerate_ellipses_case_punctuation_and_apostrophes(self):
        source = "It remains a critical route. A significant portion of the world’s petroleum passes through it."
        self.assertTrue(quote_matches("It remains a critical route... the world's petroleum passes", source))
        self.assertTrue(quote_matches("it remains, a critical route", source))
        self.assertTrue(quote_matches("A significant portion … petroleum passes through it", source))

    def test_quotes_must_keep_word_order_and_contiguity(self):
        source = "It remains a critical route for energy."
        self.assertFalse(quote_matches("It remains a route", source))
        self.assertFalse(quote_matches("critical route remains", source))
        self.assertFalse(quote_matches("route ... invented words", source))
        self.assertFalse(quote_matches("critical", source))
        self.assertFalse(quote_matches(None, source))

    def test_unusable_pairs_are_dropped_when_usable_evidence_remains(self):
        data = audit("grounded", FAITHFUL, SOURCE)
        data["evidence"][0].update(candidate_quote="One finds them stressful", source_quote="The first opposes it")
        data["evidence"].append({**data["evidence"][0], "source_quote": "invented source words"})
        self.assertEqual(validate_fidelity_assessment(data, FAITHFUL, SOURCE), (True, None))
        self.assertEqual(len(data["evidence"]), 1)
        self.assertIn("source_quote", data["dropped_evidence"][0]["problem"])

    def test_an_unusable_supported_claim_still_blocks_a_zero(self):
        data = audit()
        data["evidence"].append({"candidate_quote": "invented words", "source_quote": "fabricated source",
                                 "relation": "supported", "reason": "A faithful point."})
        self.assertFalse(validate_fidelity_assessment(data, PETS, SOURCE)[0])
        # Revalidating the cleaned data must not forget the dropped supported claim.
        self.assertFalse(validate_fidelity_assessment(data, PETS, SOURCE)[0])

    def test_prompt_treats_negation_and_paraphrase_not_word_overlap_as_evidence(self):
        prompt = build_fidelity_prompt("summarize_written_text", REVERSED, CLIMATE_SOURCE)
        for text in ("negation", "Paraphrases", "Untrusted".lower(), REVERSED, CLIMATE_SOURCE):
            self.assertIn(text, prompt)
        self.assertNotIn("captures the main ideas", prompt)


@override_settings(SOURCE_FIDELITY_ENABLED=True, SOURCE_FIDELITY_MIN_CONFIDENCE=0.9,
                   OPENAI_EVALUATION_MODEL="test-model", STRICT_FORM_POLICY_ENABLED=False)
class SourceFidelityAuditTests(TestCase):
    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_non_saving_review_never_accesses_the_cache(self, provider):
        provider.return_value = {"success": True, "data": audit()}
        with self.assertNumQueries(0):
            result = audit_source_fidelity("retell_lecture", PETS, SOURCE, use_cache=False)
        self.assertTrue(result["is_source_invalid"])
        self.assertIsNone(result["audit_cache_id"])

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_invalid_configuration_fails_explicitly_without_provider_calls(self, provider):
        for value in (float("nan"), -1, 2, True, "invalid"):
            with override_settings(SOURCE_FIDELITY_MIN_CONFIDENCE=value):
                result = audit_source_fidelity("retell_lecture", PETS, SOURCE)
                self.assertEqual(result["status"], "unavailable")
                self.assertFalse(result["retryable"])
        provider.assert_not_called()

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_quote_checked_cache_is_bound_to_source_answer_task_and_model(self, provider):
        provider.return_value = {"success": True, "data": audit()}
        first = audit_source_fidelity("summarise_group_discussion", PETS, SOURCE)
        second = audit_source_fidelity("summarise_group_discussion", PETS, SOURCE)
        self.assertTrue(first["is_source_invalid"])
        self.assertTrue(second["cached"])
        self.assertEqual(provider.call_count, 1)
        cache = EvaluationCache.objects.get()
        self.assertEqual(cache.result["input_snapshot"]["source"], SOURCE)
        self.assertEqual(cache.result["input_snapshot"]["answer"], PETS)
        with override_settings(OPENAI_EVALUATION_MODEL="other-model"):
            audit_source_fidelity("summarise_group_discussion", PETS, SOURCE)
        audit_source_fidelity("retell_lecture", PETS, SOURCE)
        provider.return_value = {"success": True, "data": audit(source=SOURCE + " Extra source.")}
        audit_source_fidelity("summarise_group_discussion", PETS, SOURCE + " Extra source.")
        provider.return_value = {"success": True, "data": audit(answer=PETS + " Another pet.")}
        audit_source_fidelity("summarise_group_discussion", PETS + " Another pet.", SOURCE)
        self.assertEqual(provider.call_count, 5)

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_invalid_cache_cannot_bypass_quote_validation(self, provider):
        provider.return_value = {"success": True, "data": audit()}
        audit_source_fidelity("retell_lecture", PETS, SOURCE)
        EvaluationCache.objects.update(result={"assessment": {"verdict": "grounded"}})
        self.assertTrue(audit_source_fidelity("retell_lecture", PETS, SOURCE)["is_source_invalid"])
        self.assertEqual(provider.call_count, 2)

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_partial_and_synonym_summaries_are_not_automatically_zeroed(self, provider):
        for verdict in ("grounded", "mixed"):
            provider.return_value = {"success": True, "data": audit(verdict, FAITHFUL)}
            result = audit_source_fidelity("retell_lecture", FAITHFUL + " " + verdict, SOURCE)
            self.assertEqual(result["status"], "pass")

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_uncertain_or_low_confidence_reviews_are_flagged_never_zeroed(self, provider):
        for data in (audit("uncertain"), audit(confidence=0.6)):
            provider.return_value = {"success": True, "data": data}
            result = audit_source_fidelity("retell_lecture", PETS, SOURCE)
            self.assertEqual(result["status"], "review")
            self.assertTrue(result["requires_review"])
            self.assertFalse(result["is_source_invalid"])
        provider.return_value = {"success": False, "error": "timeout"}
        self.assertEqual(audit_source_fidelity("retell_lecture", PETS, SOURCE)["status"], "unavailable")
        self.assertFalse(EvaluationCache.objects.exists())

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_malformed_evidence_gets_one_bounded_repair(self, provider):
        provider.side_effect = [{"success": True, "data": {}}, {"success": True, "data": audit()}]
        result = audit_source_fidelity("retell_lecture", PETS, SOURCE)
        self.assertTrue(result["is_source_invalid"])
        self.assertEqual(provider.call_count, 2)
        self.assertIn("VALIDATION REPAIR", provider.call_args.args[0])

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_repeated_invalid_evidence_is_flagged_not_cached_or_zeroed(self, provider):
        provider.return_value = {"success": True, "data": {}}
        result = audit_source_fidelity("retell_lecture", PETS, SOURCE)
        self.assertEqual(result["status"], "review")
        self.assertFalse(result["is_source_invalid"])
        self.assertEqual(provider.call_count, 2)
        self.assertFalse(EvaluationCache.objects.exists())

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_excluded_tasks_disabled_feature_and_missing_or_truncated_sources(self, provider):
        for task in ("write_essay", "describe_image", "respond_to_a_situation", "read_aloud",
                     "repeat_sentence", "write_from_dictation", "answer_short_question", "mc_multiple"):
            self.assertEqual(audit_source_fidelity(task, PETS, SOURCE)["status"], "not_applicable")
        with override_settings(SOURCE_FIDELITY_ENABLED=False):
            self.assertEqual(audit_source_fidelity("retell_lecture", PETS, SOURCE)["status"], "not_applicable")
        for source in ("", SOURCE * 1000):
            result = audit_source_fidelity("retell_lecture", PETS, source)
            self.assertEqual(result["status"], "unavailable")
            self.assertFalse(result["retryable"])
        provider.assert_not_called()


@override_settings(SOURCE_FIDELITY_ENABLED=True, OPENAI_EVALUATION_MODEL="test-model",
                   STRICT_FORM_POLICY_ENABLED=False)
class SourceFidelityPipelineTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Speaking")
        self.subsection = SubSection.objects.create(
            name="summarise_group_discussion", section=section, evaluation_type="ai",
            ai_input_type="audio", rubric={"content": {"max": 6}, "oral_fluency": {"max": 5},
                                          "pronunciation": {"max": 5}},
            trait_skill_map={"content": ["listening"], "oral_fluency": ["speaking"],
                             "pronunciation": ["speaking"]},
        )

    def evaluate(self, answer=PETS):
        return run_evaluation_for_subsection(self.subsection, SOURCE, {
            "reference_answer": SOURCE, "answer_data": answer,
        })

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    def test_diagnostic_dry_run_and_provider_review_do_not_change_saved_data(self, reviewer):
        reviewer.return_value = {"success": True, "data": audit()}
        q = Question.objects.create(name="Non-saving QA", subsection=self.subsection, correct_answer=SOURCE)
        r = SingleResponse.objects.create(question=q, answer_data=PETS, evaluated=True,
                                          evaluation_result=graded(), speaking_score_awarded=4.25,
                                          listening_score_awarded=7.5)
        output = StringIO()
        call_command("check_response_source_fidelity", response_id=r.pk, stdout=output)
        reviewer.assert_not_called()
        self.assertIn("Dry run", output.getvalue())
        call_command("check_response_source_fidelity", response_id=r.pk, evaluate=True, stdout=output)
        reviewer.assert_called_once()
        r.refresh_from_db()
        self.assertEqual(r.evaluation_result, graded())
        self.assertEqual(r.speaking_score_awarded, 4.25)
        self.assertEqual(r.listening_score_awarded, 7.5)
        self.assertFalse(EvaluationCache.objects.exists())

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_meaning_reversed_swt_is_zeroed_even_with_high_initial_content(self, grader, reviewer):
        self.subsection.name = "summarize_written_text"
        grader.return_value = {"success": True, "data": graded(REVERSED)}
        reviewer.return_value = {"success": True, "data": audit("contradictory", REVERSED, CLIMATE_SOURCE)}
        result = run_evaluation_for_subsection(self.subsection, CLIMATE_SOURCE, {"answer_data": REVERSED})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        self.assertEqual(result["integrity_checks"]["source_fidelity"]["assessment"]["verdict"], "contradictory")

    @override_settings(STRICT_FORM_POLICY_ENABLED=True)
    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_underlength_essay_and_75_word_sst_still_zero_before_either_provider(self, grader, reviewer):
        for task, count in (("write_essay", 187), ("write_essay", 143), ("summarize_spoken_text", 75)):
            self.subsection.name = task
            result = self.evaluate("word " * count)
            self.assertTrue(result["ok"])
            self.assertEqual(result["evaluation"]["weighted_score"], 0)
            self.assertFalse(result["provider_called"])
        grader.assert_not_called()
        reviewer.assert_not_called()

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_hitha_regression_wrong_high_content_and_template_pass_cannot_award_marks(self, grader, reviewer):
        grader.return_value = {"success": True, "data": graded()}
        reviewer.return_value = {"success": True, "data": audit()}
        result = self.evaluate()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        override = result["score_overrides"][-1]
        self.assertEqual(override["code"], "source_fidelity_failed")
        self.assertEqual(override["original_scores"]["content"]["score"], 5)
        self.assertIn("source_fidelity", result["integrity_checks"])
        question = SimpleNamespace(subsection=self.subsection, speaking_score_max=8.5,
                                   listening_score_max=9, reading_score_max=0, writing_score_max=0)
        for mode in ("legacy", "shadow", "v2"):
            evidence = compile_response_score_evidence(question, result, mode=mode)
            self.assertTrue(all(p["score"] == 0 for p in evidence["promoted"]["skills"].values()))
        cached = self.evaluate()
        self.assertTrue(cached["cached"])
        self.assertEqual(cached["evaluation"]["weighted_score"], 0)
        self.assertEqual(grader.call_count, 1)
        self.assertEqual(reviewer.call_count, 1)

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_all_four_summary_tasks_use_the_review_but_essay_disagreement_does_not(self, grader, reviewer):
        grader.return_value = {"success": True, "data": graded()}
        reviewer.return_value = {"success": True, "data": audit()}
        for task in ("retell_lecture", "summarise_group_discussion", "summarize_spoken_text", "summarize_written_text"):
            self.subsection.name = task
            self.assertEqual(self.evaluate()["evaluation"]["weighted_score"], 0)
        self.assertEqual(reviewer.call_count, 4)
        self.subsection.name = "write_essay"
        self.assertTrue(self.evaluate()["ok"])
        self.assertEqual(reviewer.call_count, 4)

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_faithful_paraphrase_preserves_grading_and_audit_is_independent(self, grader, reviewer):
        grader.return_value = {"success": True, "data": graded(FAITHFUL)}
        reviewer.return_value = {"success": True, "data": audit("grounded", FAITHFUL)}
        result = self.evaluate(FAITHFUL)
        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 5)
        self.assertNotIn("score_overrides", result)
        review_prompt = reviewer.call_args.args[0]
        self.assertNotIn("captures the main ideas", review_prompt)
        self.assertNotIn('"scores"', review_prompt)

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_uncertain_review_keeps_normal_grading_and_is_flagged(self, grader, reviewer):
        grader.return_value = {"success": True, "data": graded()}
        reviewer.return_value = {"success": True, "data": audit("uncertain")}
        result = self.evaluate()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 5)
        self.assertEqual(result["integrity_checks"]["source_fidelity"]["status"], "review")
        self.assertNotIn("score_overrides", result)

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_provider_failure_still_fails_the_evaluation_for_retry(self, grader, reviewer):
        grader.return_value = {"success": True, "data": graded()}
        reviewer.return_value = {"success": False, "error": "timeout"}
        result = self.evaluate()
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "source_fidelity_unavailable")
        self.assertTrue(result["retryable"])

    @patch("examinor.services.source_fidelity.evaluate_with_openai")
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_single_and_exam_tasks_store_zero_with_original_marks_and_reason(self, grader, reviewer):
        grader.return_value = {"success": True, "data": graded()}
        reviewer.return_value = {"success": True, "data": audit()}
        paper = MockTest.objects.create(title="Source QA", scoring_mode="v2")
        section = MockTestSection.objects.create(mock_test=paper, section=self.subsection.section, order=1)
        q = Question.objects.create(name="Source QA", subsection=self.subsection, correct_answer=SOURCE,
                                    mock_test_section=section, speaking_score_max=8.5, listening_score_max=9)
        session = UserMockTestSession.objects.create(mock_test=paper, session_id="source-qa", name="QA", scoring_mode="v2")
        values = {"question": q, "answer_audio": "qa/saved.webm",
                  "transcribed_audio_data": {"transcription": {"text": PETS}}}
        for row, task in (
            (SingleResponse.objects.create(name="QA", scoring_mode="v2", **values), evaluate_single_response),
            (UserResponse.objects.create(user_session=session, mock_test=paper, **values), evaluate_user_response),
        ):
            task.run(row.pk, q.pk)
            row.refresh_from_db()
            self.assertTrue(row.evaluated)
            self.assertEqual(row.speaking_score_awarded, 0)
            self.assertEqual(row.listening_score_awarded, 0)
            self.assertTrue(row.evaluation_result["integrity_checks"]["source_fidelity"]["is_source_invalid"])
            self.assertEqual(row.evaluation_result["score_overrides"][-1]["original_scores"]["content"]["score"], 5)
