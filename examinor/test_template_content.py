from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from examinor.models import EvaluationCache
from examinor.scoring.response_scores import compile_response_score_evidence
from examinor.services.orchestrator import run_evaluation_for_subsection
from examinor.services.prompt_builder import build_prompt
from examinor.services.template_content import (
    apply_template_content_override, inspect_template_content,
    template_assessment_required, validate_template_assessment,
)
from mocktest.models import (
    MockTest, MockTestSection, Question, Section, SingleResponse, SubSection,
    UserMockTestSession, UserResponse,
)
from mocktest.tasks import apply_answer_integrity_policy, evaluate_single_response, evaluate_user_response


GENERIC = (
    "This subject opens an interesting opportunity to consider several important aspects. "
    "A balanced understanding can provide valuable insights for everyone involved. "
    "Different perspectives deserve careful consideration because each dimension contributes "
    "to a broader picture. With appropriate attention, useful conclusions can support future progress."
)
ESSAY_GENERIC = GENERIC + (
    " The modern world presents many opportunities alongside a range of challenges. "
    "Society must approach such matters thoughtfully and seek practical possibilities. "
    "A comprehensive evaluation encourages constructive development in numerous areas. "
    "In conclusion, taking a balanced approach allows individuals and communities to "
    "move forward together while considering all relevant aspects of this important topic."
)
SPECIFIC = (
    "Could we move the team meeting to Thursday afternoon because the client audit "
    "runs throughout Wednesday? I can send the updated figures on Tuesday so everyone "
    "has time to prepare. Please let me know whether that alternative suits your schedule."
)
QUESTION = "Ask your manager to reschedule a Wednesday meeting because of a client audit."


def assessment(answer=GENERIC, *, verdict="template_dominated", confidence=0.99):
    return {
        "verdict": verdict, "confidence": confidence,
        "addresses_task": verdict == "substantive",
        "generic_passages": [] if verdict == "substantive" else [{"text": answer, "reason": "Interchangeable prose does not make the requested request or explain a relevant point."}],
        "specific_points": [{"text": answer, "reason": "Makes the requested scheduling request and explains the client-audit conflict."}] if verdict == "substantive" else [],
        "reason": "No meaningful response to the communication goal." if verdict != "substantive" else "Addresses the communication goal with concrete support.",
    }


def provider_data(answer=GENERIC, **options):
    return {
        "scores": {"content": {"score": 4, "max": 6}},
        "feedback": {"summary": "Initial rubric feedback", "errors": []},
        "template_assessment": assessment(answer, **options),
    }


class TemplateContentTests(SimpleTestCase):
    def inspect(self, answer=GENERIC, data=None, **kwargs):
        return inspect_template_content(
            data or provider_data(answer), "respond_to_a_situation", answer,
            source_available=kwargs.pop("source_available", True), **kwargs,
        )

    def test_unfamiliar_nonrepeated_generic_script_is_blocked_with_quote_evidence(self):
        result = self.inspect()
        self.assertTrue(result["is_template_dominated"])
        self.assertEqual(result["generic_word_ratio"], 1)
        self.assertEqual(result["status"], "hard_zero")

    def test_same_policy_covers_all_seven_descriptive_tasks(self):
        for task in (
            "describe_image", "retell_lecture", "summarise_group_discussion",
            "respond_to_a_situation", "summarize_written_text", "summarize_spoken_text", "write_essay",
        ):
            answer = ESSAY_GENERIC if task == "write_essay" else GENERIC
            with self.subTest(task=task):
                result = inspect_template_content(provider_data(answer), task, answer, source_available=True)
                self.assertTrue(result["is_template_dominated"])

    def test_substantive_answer_and_familiar_structure_are_allowed(self):
        result = self.inspect(SPECIFIC, provider_data(SPECIFIC, verdict="substantive"))
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["is_template_dominated"])

    def test_concrete_relevant_content_vetoes_automatic_template_zero(self):
        answer = GENERIC + " " + SPECIFIC
        data = provider_data(GENERIC)
        data["template_assessment"]["specific_points"] = [{"text": SPECIFIC, "reason": "Meaningful request tied to the actual scheduling conflict."}]
        result = self.inspect(answer, data)
        self.assertEqual(result["status"], "review")
        self.assertFalse(result["is_template_dominated"])

    def test_uncertain_low_confidence_missing_source_or_truncated_context_is_not_zeroed(self):
        cases = (
            ({"verdict": "uncertain"}, {}),
            ({"confidence": 0.7}, {}),
            ({}, {"source_available": False}),
            ({}, {"context_complete": False}),
        )
        for options, context in cases:
            with self.subTest(options=options, context=context):
                result = self.inspect(data=provider_data(**options), **context)
                self.assertTrue(result["requires_review"])
                self.assertFalse(result["is_template_dominated"])

    def test_overlapping_generic_quotes_are_not_double_counted(self):
        data = provider_data()
        data["template_assessment"]["generic_passages"] *= 3
        self.assertEqual(self.inspect(data=data)["generic_word_ratio"], 1)

    def test_specific_content_outweighing_generic_quotes_prevents_a_zero(self):
        data = provider_data(GENERIC)
        data["template_assessment"]["specific_points"] = [{"text": SPECIFIC, "reason": "Makes the actual request."}]
        result = self.inspect(GENERIC + " " + SPECIFIC * 4, data)
        self.assertFalse(result["is_template_dominated"])

    def test_partly_quoted_template_with_token_specific_points_is_zeroed(self):
        # The evaluator quotes sample generic phrases, not every generic word, and may
        # list a generic fragment as specific; its confident verdict still decides.
        sentences = GENERIC.split(". ")
        data = provider_data(GENERIC)
        data["template_assessment"]["generic_passages"] = [
            {"text": sentences[0], "reason": "Interchangeable opening."},
            {"text": sentences[2], "reason": "Generic filler."},
        ]
        data["template_assessment"]["specific_points"] = [{"text": "useful conclusions can support", "reason": "Vague."}]
        result = self.inspect(GENERIC + " " + GENERIC.lower(), data)
        self.assertLess(result["generic_word_ratio"], 0.7)
        self.assertTrue(result["is_template_dominated"])

    def test_too_few_generic_words_or_a_task_answer_never_zero(self):
        data = provider_data()
        data["template_assessment"]["generic_passages"] = [{"text": "deserve careful consideration because each", "reason": "Generic."}]
        self.assertFalse(self.inspect(data=data)["is_template_dominated"])
        data = provider_data()
        data["template_assessment"]["addresses_task"] = True
        self.assertFalse(self.inspect(data=data)["is_template_dominated"])

    def test_structurally_invalid_assessments_are_rejected(self):
        variants = []
        variants.append({"scores": {}})
        for key, value in (("confidence", float("nan")), ("confidence", True), ("addresses_task", "false"), ("reason", "")):
            data = provider_data()
            data["template_assessment"][key] = value
            variants.append(data)
        data = provider_data()
        data["template_assessment"]["generic_passages"] = "not a list"
        variants.append(data)
        for data in variants:
            with self.subTest(data=data):
                self.assertFalse(validate_template_assessment(data, "respond_to_a_situation", GENERIC)[0])

    def test_unusable_evidence_is_dropped_and_cannot_cause_a_zero(self):
        invented = provider_data("Words that are not in the saved answer")
        overlapping = provider_data()
        overlapping["template_assessment"]["specific_points"] = deepcopy(
            overlapping["template_assessment"]["generic_passages"]
        )
        unsupported = provider_data()
        unsupported["template_assessment"].update(verdict="substantive", addresses_task=True)
        for data in (invented, overlapping, unsupported):
            with self.subTest(data=data):
                # Strict validation asks for a repair and leaves the output untouched.
                before = deepcopy(data)
                self.assertFalse(validate_template_assessment(data, "respond_to_a_situation", GENERIC, strict=True)[0])
                self.assertEqual(data, before)
                self.assertEqual(validate_template_assessment(data, "respond_to_a_situation", GENERIC), (True, None))
                result = self.inspect(GENERIC, data)
                self.assertFalse(result["is_template_dominated"])
                self.assertEqual(result["status"], "review")
        self.assertEqual(invented["template_assessment"]["generic_passages"], [])
        self.assertEqual(invented["template_assessment"]["dropped_evidence"][0]["problem"], "not an exact candidate quote")
        self.assertEqual(overlapping["template_assessment"]["generic_passages"], [])
        self.assertEqual(unsupported["template_assessment"]["verdict"], "uncertain")
        self.assertEqual(unsupported["template_assessment"]["downgraded_from"], "substantive")

    def test_short_generic_quote_is_dropped_without_losing_the_rest(self):
        data = provider_data()
        data["template_assessment"]["generic_passages"].append(
            {"text": "several important aspects", "reason": "Generic filler."}
        )
        self.assertEqual(validate_template_assessment(data, "respond_to_a_situation", GENERIC), (True, None))
        self.assertEqual(len(data["template_assessment"]["generic_passages"]), 1)
        self.assertEqual(data["template_assessment"]["dropped_evidence"][0]["problem"], "fewer than 4 words")
        self.assertTrue(self.inspect(GENERIC, data)["is_template_dominated"])

    def test_losing_specific_evidence_downgrades_a_template_verdict(self):
        data = provider_data()
        data["template_assessment"]["specific_points"] = [{"text": "invented content", "reason": "Relevant."}]
        self.assertEqual(validate_template_assessment(data, "respond_to_a_situation", GENERIC), (True, None))
        self.assertEqual(data["template_assessment"]["verdict"], "uncertain")
        self.assertFalse(self.inspect(GENERIC, data)["is_template_dominated"])

    def test_short_and_fixed_answer_tasks_do_not_require_this_assessment(self):
        for task in ("read_aloud", "repeat_sentence", "write_from_dictation", "answer_short_question", "fib_dropdown", "mc_multiple"):
            self.assertFalse(template_assessment_required(task, GENERIC))
        self.assertFalse(template_assessment_required("write_essay", GENERIC))
        self.assertFalse(template_assessment_required("respond_to_a_situation", "Could we reschedule?"))

    @override_settings(TEMPLATE_CONTENT_CONFIG={"enabled": False})
    def test_semantic_feature_can_be_disabled_independently(self):
        self.assertFalse(template_assessment_required("write_essay", ESSAY_GENERIC))

    def test_override_keeps_original_marks_and_explains_the_zero(self):
        result = apply_template_content_override({"ok": True, "evaluation": provider_data()}, self.inspect())
        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 0)
        self.assertEqual(result["score_overrides"][0]["original_scores"]["content"]["score"], 4)
        self.assertIn("Generic template", result["evaluation"]["feedback"]["summary"])
        question = SimpleNamespace(
            subsection=SimpleNamespace(name="respond_to_a_situation", trait_skill_map={"content": ["speaking"]}),
            speaking_score_max=6, reading_score_max=0, writing_score_max=0, listening_score_max=0,
        )
        for mode in ("legacy", "shadow", "v2"):
            with self.subTest(mode=mode):
                evidence = compile_response_score_evidence(question, result, mode=mode)
                self.assertTrue(all(p["score"] == 0 for p in evidence["promoted"]["skills"].values()))


@override_settings(STRICT_FORM_POLICY_ENABLED=False)
class TemplateContentOrchestratorTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Speaking")
        self.subsection = SubSection.objects.create(section=section, name="respond_to_a_situation", rubric={"content": {"max": 6}})

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_cache_keeps_raw_scores_and_reapplies_current_gate(self, evaluate):
        evaluate.return_value = {"success": True, "data": provider_data()}
        payload = {"answer_data": GENERIC}
        first = run_evaluation_for_subsection(self.subsection, QUESTION, payload)
        second = run_evaluation_for_subsection(self.subsection, QUESTION, payload)
        self.assertTrue(first["integrity_checks"]["template_content"]["is_template_dominated"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["evaluation"]["weighted_score"], 0)
        self.assertEqual(EvaluationCache.objects.get().result["scores"]["content"]["score"], 4)
        with override_settings(TEMPLATE_CONTENT_CONFIG={"minimum_confidence": 1.0}):
            reviewed = run_evaluation_for_subsection(self.subsection, QUESTION, payload)
        self.assertEqual(reviewed["evaluation"]["weighted_score"], 4)
        self.assertEqual(reviewed["integrity_checks"]["template_content"]["status"], "review")
        self.assertEqual(evaluate.call_count, 1)

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_absent_assessment_gets_bounded_repair_then_fails_without_scoring(self, evaluate):
        evaluate.return_value = {"success": True, "data": {"scores": {"content": {"score": 4, "max": 6}}}}
        result = run_evaluation_for_subsection(self.subsection, QUESTION, {"answer_data": GENERIC})
        self.assertFalse(result["ok"])
        self.assertIn("Missing template_assessment", result["error"])
        self.assertEqual(evaluate.call_count, 2)
        self.assertFalse(EvaluationCache.objects.exists())

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_fabricated_evidence_can_be_repaired_without_accepting_initial_marks(self, evaluate):
        evaluate.side_effect = [
            {"success": True, "data": provider_data("Fabricated candidate quotation not in this answer")},
            {"success": True, "data": provider_data()},
        ]
        result = run_evaluation_for_subsection(self.subsection, QUESTION, {"answer_data": GENERIC})
        self.assertTrue(result["ok"])
        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        self.assertEqual(evaluate.call_count, 2)

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_unrepaired_evidence_is_reviewed_instead_of_failing_the_answer(self, evaluate):
        short_quote = provider_data()
        short_quote["template_assessment"]["generic_passages"].append(
            {"text": "several important aspects", "reason": "Generic filler."}
        )
        evaluate.side_effect = [
            {"success": True, "data": provider_data("Fabricated candidate quotation not in this answer")},
            {"success": True, "data": provider_data("Still not a quotation from this answer")},
        ]
        result = run_evaluation_for_subsection(self.subsection, QUESTION, {"answer_data": GENERIC})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["integrity_checks"]["template_content"]["status"], "review")
        self.assertEqual(evaluate.call_count, 2)

        EvaluationCache.objects.all().delete()
        evaluate.reset_mock()
        evaluate.side_effect = [{"success": True, "data": deepcopy(short_quote)} for _ in range(2)]
        result = run_evaluation_for_subsection(self.subsection, QUESTION, {"answer_data": GENERIC})
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["integrity_checks"]["template_content"]["is_template_dominated"])

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_language_audit_cannot_erase_a_valid_template_finding(self, evaluate):
        self.subsection.name = "write_essay"
        self.subsection.rubric = {"content": {"max": 6}, "grammar": {"max": 2}}
        first = provider_data(ESSAY_GENERIC)
        first["scores"]["grammar"] = {"score": 2, "max": 2}
        second = deepcopy(first)
        del second["template_assessment"]
        evaluate.side_effect = [{"success": True, "data": data} for data in (first, second)]
        result = run_evaluation_for_subsection(self.subsection, QUESTION, {"answer_data": ESSAY_GENERIC})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        self.assertTrue(result["integrity_checks"]["template_content"]["is_template_dominated"])

    def test_prompt_requests_source_grounding_and_changes_when_gate_disabled(self):
        prompt, key = build_prompt("respond_to_a_situation", QUESTION, {"answer_data": GENERIC}, {})
        self.assertIn("template_assessment", prompt)
        self.assertIn("exact, case-preserving", prompt)
        with override_settings(TEMPLATE_CONTENT_CONFIG={"enabled": False}):
            disabled_prompt, disabled_key = build_prompt("respond_to_a_situation", QUESTION, {"answer_data": GENERIC}, {})
        self.assertNotEqual(key, disabled_key)
        self.assertNotIn("template_assessment", disabled_prompt)


@override_settings(STRICT_FORM_POLICY_ENABLED=False)
class TemplateContentTaskTests(TestCase):
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_both_response_models_and_both_input_types_store_zero_and_evidence(self, evaluate):
        for task_name, answer in (("respond_to_a_situation", GENERIC), ("write_essay", ESSAY_GENERIC)):
            spoken = task_name == "respond_to_a_situation"
            skill = "speaking" if spoken else "writing"
            section = Section.objects.create(name=skill.title())
            rubric = {"content": {"max": 6}}
            data = provider_data(answer)
            if not spoken:
                rubric["form"] = {"max": 2}
                data["scores"]["form"] = {"score": 2, "max": 2}
            else:
                for trait in ("oral_fluency", "pronunciation"):
                    rubric[trait] = {"max": 5}
                    data["scores"][trait] = {"score": 5, "max": 5}
            evaluate.return_value = {"success": True, "data": data}
            subsection = SubSection.objects.create(
                section=section, name=task_name, evaluation_type="ai", ai_input_type="audio" if spoken else "text",
                rubric=rubric, trait_skill_map={trait: [skill] for trait in rubric},
            )
            paper = MockTest.objects.create(title=task_name, scoring_mode="v2")
            paper_section = MockTestSection.objects.create(mock_test=paper, section=section, order=1)
            question = Question.objects.create(
                text=QUESTION, name=task_name, subsection=subsection, mock_test_section=paper_section,
                **{f"{skill}_score_max": 16 if spoken else 8},
            )
            session = UserMockTestSession.objects.create(mock_test=paper, session_id=task_name, name="Template QA", scoring_mode="v2")
            common = {"question": question, "answer_data": answer}
            if spoken:
                common.update(answer_audio="qa/template.webm", transcribed_audio_data={"transcription": {"text": answer}})
            rows = (
                (SingleResponse.objects.create(name="QA", scoring_mode="v2", **common), evaluate_single_response),
                (UserResponse.objects.create(mock_test=paper, user_session=session, **common), evaluate_user_response),
            )
            for response, task in rows:
                with self.subTest(task=task_name, model=type(response).__name__):
                    execution = task.apply(args=(response.pk, question.pk))
                    self.assertTrue(execution.successful(), execution.result)
                    response.refresh_from_db()
                    self.assertTrue(response.evaluated)
                    self.assertEqual(getattr(response, f"{skill}_score_awarded"), 0)
                    self.assertTrue(response.evaluation_result["integrity_checks"]["template_content"]["is_template_dominated"])
                    self.assertEqual(response.evaluation_result["score_overrides"][0]["code"], "template_content_dominated")

    @patch("mocktest.tasks.inspect_answer_integrity")
    def test_known_framework_match_does_not_overrule_valid_specific_content(self, inspect):
        inspect.return_value = {"checks": {
            "repetition": {"enabled": False, "evidence": {"is_repetitive": False, "status": "disabled"}},
            "known_template": {"enabled": True, "evidence": {
                "is_template_dominated": True, "status": "hard_zero", "matched_template": {"id": 1},
                "answer_match_ratio": 0.8, "original_word_count": 10,
                "detector_version": "known-answer-template-v1",
            }},
        }}
        semantic = inspect_template_content(provider_data(SPECIFIC, verdict="substantive"), "respond_to_a_situation", SPECIFIC, source_available=True)
        result = {"ok": True, "evaluation": provider_data(SPECIFIC, verdict="substantive"), "integrity_checks": {"template_content": semantic}}
        response = SimpleNamespace(answer_data=SPECIFIC, transcribed_audio_data=None, question=SimpleNamespace(text=QUESTION), pk=1)
        result = apply_answer_integrity_policy(response, result, SimpleNamespace(name="respond_to_a_situation"))
        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 4)
        self.assertFalse(result["integrity_checks"]["known_template"]["is_template_dominated"])
        self.assertTrue(result["integrity_checks"]["known_template"]["lexical_match_would_block"])
