import csv
import tempfile
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from examinor.scoring.response_scores import (
    LEGACY_SCORING_VERSION,
    ResponseScoringError,
    compile_response_score_evidence,
    configured_scoring_mode,
    promoted_skill_values,
    response_scoring_mode,
)
from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    Section,
    SingleResponse,
    SubSection,
    UserMockTestSession,
    UserResponse,
)
from mocktest.services.session_finalization import (
    complete_session_submission,
    create_session_manifest,
    mark_session_question_answered,
)


def question(
    subsection,
    trait_skill_map,
    *,
    speaking=0,
    writing=0,
    reading=0,
    listening=0,
):
    return SimpleNamespace(
        subsection=SimpleNamespace(
            name=subsection,
            trait_skill_map=trait_skill_map,
        ),
        speaking_score_max=speaking,
        writing_score_max=writing,
        reading_score_max=reading,
        listening_score_max=listening,
    )


def evaluation(scores):
    return {"ok": True, "evaluation": {"scores": scores}}


class ResponseScoreEvidenceTests(SimpleTestCase):
    def test_read_aloud_awards_speaking_only_under_current_policy(self):
        evidence = compile_response_score_evidence(
            question(
                "read_aloud",
                {
                    "content": ["reading", "speaking"],
                    "oral_fluency": ["speaking"],
                    "pronunciation": ["speaking"],
                },
                speaking=1.5,
                reading=6,
            ),
            evaluation({
                "content": {"score": 6, "max": 6},
                "oral_fluency": {"score": 5, "max": 5},
                "pronunciation": {"score": 4, "max": 5},
            }),
            mode="v2",
        )

        promoted = promoted_skill_values(evidence)
        self.assertEqual(promoted["reading"], 0)
        self.assertAlmostEqual(promoted["speaking"], 1.40625)
        self.assertNotIn("reading", evidence["promoted"]["skills"])

    def test_repeat_sentence_zero_content_gates_all_skill_awards(self):
        evidence = compile_response_score_evidence(
            question(
                "repeat_sentence",
                {
                    "content": ["listening", "speaking"],
                    "oral_fluency": ["speaking"],
                    "pronunciation": ["speaking"],
                },
                speaking=1.4,
                listening=1.5,
            ),
            evaluation({
                "content": {"score": 0, "max": 3},
                "oral_fluency": {"score": 4, "max": 5},
                "pronunciation": {"score": 5, "max": 5},
            }),
            mode="v2",
        )

        self.assertTrue(evidence["promoted"]["gate"]["applied"])
        self.assertEqual(promoted_skill_values(evidence)["speaking"], 0)
        self.assertEqual(promoted_skill_values(evidence)["listening"], 0)

    def test_shadow_mode_preserves_legacy_score_and_records_v2_delta(self):
        evidence = compile_response_score_evidence(
            question(
                "fib_drag_drop",
                {"reading": ["reading"]},
                reading=5,
            ),
            evaluation({"reading": {"score": 0.8, "max": 1}}),
            mode="shadow",
        )

        self.assertEqual(evidence["promoted_version"], LEGACY_SCORING_VERSION)
        self.assertAlmostEqual(evidence["promoted"]["skills"]["reading"]["score"], 0.8)
        self.assertAlmostEqual(evidence["v2"]["skills"]["reading"]["score"], 4)
        self.assertAlmostEqual(evidence["delta"]["reading"], 3.2)

    def test_v2_mode_promotes_compiled_score(self):
        evidence = compile_response_score_evidence(
            question(
                "l_fill_in_blanks",
                {"listening": ["listening"]},
                listening=4,
            ),
            evaluation({"listening": {"score": 1, "max": 1}}),
            mode="v2",
        )

        self.assertEqual(evidence["promoted_version"], "pte-score-v2")
        self.assertEqual(promoted_skill_values(evidence)["listening"], 4)

    def test_shadow_mode_records_contract_error_without_disrupting_legacy(self):
        evidence = compile_response_score_evidence(
            question(
                "fib_dropdown",
                {"reading": ["reading"]},
                reading=0,
            ),
            evaluation({"reading": {"score": 1, "max": 1}}),
            mode="shadow",
        )

        self.assertIsNone(evidence["v2"])
        self.assertIn("Missing positive question maxima", evidence["v2_error"])
        self.assertEqual(promoted_skill_values(evidence)["reading"], 0)

    def test_shadow_mode_promotes_exact_multiple_answer_score(self):
        evidence = compile_response_score_evidence(
            question(
                "mc_multiple",
                {"reading": ["reading"]},
                reading=2.5,
            ),
            {
                "ok": True,
                "evaluation": {
                    "scores": {"reading": {"score": 0.67, "max": 1}},
                    "answer_scoring": {
                        "raw_points": 2,
                        "maximum_raw_points": 3,
                    },
                },
            },
            mode="shadow",
        )

        self.assertEqual(evidence["promoted_version"], "pte-score-v2")
        self.assertAlmostEqual(evidence["legacy"]["skills"]["reading"]["score"], 0.67)
        self.assertAlmostEqual(evidence["promoted"]["skills"]["reading"]["score"], 5 / 3)
        self.assertEqual(
            evidence["promotion_reason"],
            "Task requires proportional multiple-answer scoring.",
        )

    def test_explicit_legacy_mode_preserves_multiple_answer_legacy_score(self):
        evidence = compile_response_score_evidence(
            question(
                "l_mc_multiple",
                {"listening": ["listening"]},
                listening=1.5,
            ),
            evaluation({"listening": {"score": 1 / 3, "max": 1}}),
            mode="legacy",
        )

        self.assertEqual(evidence["promoted_version"], LEGACY_SCORING_VERSION)
        self.assertAlmostEqual(
            evidence["promoted"]["skills"]["listening"]["score"],
            1 / 3,
        )

    def test_v2_mode_fails_closed_on_contract_error(self):
        with self.assertRaisesRegex(ResponseScoringError, "V2 score compilation failed"):
            compile_response_score_evidence(
                question(
                    "fib_dropdown",
                    {"reading": ["reading"]},
                    reading=0,
                ),
                evaluation({"reading": {"score": 1, "max": 1}}),
                mode="v2",
            )

    def test_task_specific_v2_gate_does_not_repeat_legacy_global_gate(self):
        evidence = compile_response_score_evidence(
            question(
                "answer_short_question",
                {
                    "content": ["listening"],
                    "accuracy": ["listening"],
                },
                listening=2,
            ),
            evaluation(
                {
                    "content": {"score": 0, "max": 1},
                    "accuracy": {"score": 1, "max": 1},
                }
            ),
            mode="shadow",
        )

        self.assertEqual(evidence["legacy"]["skills"]["listening"]["score"], 0)
        self.assertEqual(evidence["v2"]["skills"]["listening"]["score"], 1)

    @override_settings(EVALUATION_SCORING_MODE="not-a-mode")
    def test_invalid_configured_mode_is_rejected(self):
        with self.assertRaisesRegex(ResponseScoringError, "Unsupported"):
            configured_scoring_mode()


@override_settings(EVALUATION_SCORING_MODE="shadow")
class ResponseScorePersistenceTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Reading")
        subsection = SubSection.objects.create(
            section=section,
            name="fib_drag_drop",
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
            trait_skill_map={"reading": ["reading"]},
        )
        mock_test = MockTest.objects.create(title="Scoring shadow test")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
        )
        self.question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            text="Complete the blanks.",
            reading_score_max=5,
        )
        self.mock_test = mock_test
        self.result = evaluation({"reading": {"score": 0.8, "max": 1}})

    def test_user_response_persists_shadow_without_changing_live_score(self):
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="shadow-user-response",
            mock_test=self.mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=self.mock_test,
            question=self.question,
            evaluation_result=self.result,
        )

        response.apply_skill_scores()
        response.refresh_from_db()

        evidence = response.evaluation_result["scoring_evidence"]
        self.assertEqual(response.reading_score_awarded, 0.8)
        self.assertEqual(evidence["promoted_version"], LEGACY_SCORING_VERSION)
        self.assertEqual(evidence["v2"]["skills"]["reading"]["score"], 4)

    def test_single_response_uses_same_shadow_compiler(self):
        response = SingleResponse.objects.create(
            question=self.question,
            scoring_mode="shadow",
            evaluation_result=self.result,
        )

        response.apply_skill_scores()
        response.refresh_from_db()

        evidence = response.evaluation_result["scoring_evidence"]
        self.assertEqual(response.reading_score_awarded, 0.8)
        self.assertEqual(evidence["v2"]["skills"]["reading"]["score"], 4)

    def test_single_response_keeps_pinned_v2_when_global_mode_is_shadow(self):
        response = SingleResponse.objects.create(
            question=self.question,
            scoring_mode="v2",
            evaluation_result=self.result,
        )

        response.apply_skill_scores()
        response.refresh_from_db()

        evidence = response.evaluation_result["scoring_evidence"]
        self.assertEqual(response_scoring_mode(response), "v2")
        self.assertEqual(evidence["promoted_version"], "pte-score-v2")
        self.assertEqual(response.reading_score_awarded, 4)

    def test_user_response_keeps_session_mode_when_global_mode_changes(self):
        with self.settings(EVALUATION_SCORING_MODE="shadow"):
            session = UserMockTestSession.objects.create(
                name="Candidate",
                session_id="pinned-shadow-session",
                mock_test=self.mock_test,
            )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=self.mock_test,
            question=self.question,
            evaluation_result=self.result,
        )

        with self.settings(EVALUATION_SCORING_MODE="v2"):
            response.apply_skill_scores()

        response.refresh_from_db()
        evidence = response.evaluation_result["scoring_evidence"]
        self.assertEqual(session.scoring_mode, "shadow")
        self.assertEqual(response_scoring_mode(response), "shadow")
        self.assertEqual(evidence["promoted_version"], LEGACY_SCORING_VERSION)
        self.assertEqual(response.reading_score_awarded, 0.8)

    def test_v2_session_remains_v2_when_global_mode_returns_to_shadow(self):
        with self.settings(EVALUATION_SCORING_MODE="v2"):
            session = UserMockTestSession.objects.create(
                name="Candidate",
                session_id="pinned-v2-session",
                mock_test=self.mock_test,
            )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=self.mock_test,
            question=self.question,
            evaluation_result=self.result,
        )

        with self.settings(EVALUATION_SCORING_MODE="shadow"):
            response.apply_skill_scores()

        response.refresh_from_db()
        evidence = response.evaluation_result["scoring_evidence"]
        self.assertEqual(session.scoring_mode, "v2")
        self.assertEqual(response_scoring_mode(response), "v2")
        self.assertEqual(evidence["promoted_version"], "pte-score-v2")
        self.assertEqual(response.reading_score_awarded, 4)

    def test_delta_report_is_read_only_and_covers_both_response_models(self):
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="delta-report-session",
            mock_test=self.mock_test,
        )
        user_response = UserResponse.objects.create(
            user_session=session,
            mock_test=self.mock_test,
            question=self.question,
            evaluation_result=self.result,
        )
        single_response = SingleResponse.objects.create(
            question=self.question,
            evaluation_result=self.result,
        )
        user_response.apply_skill_scores()
        single_response.apply_skill_scores()

        with tempfile.TemporaryDirectory() as directory:
            output = f"{directory}/deltas.csv"
            stdout = StringIO()
            call_command(
                "report_scoring_v2_deltas",
                "--output",
                output,
                stdout=stdout,
            )
            with open(output, encoding="utf-8") as report:
                rows = list(csv.DictReader(report))

        user_response.refresh_from_db()
        single_response.refresh_from_db()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["score_changes"] for row in rows}, {"yes"})
        self.assertEqual({row["delta_reading"] for row in rows}, {"3.2"})
        self.assertEqual(user_response.reading_score_awarded, 0.8)
        self.assertEqual(single_response.reading_score_awarded, 0.8)
        self.assertIn(
            "fib_drag_drop: checked=2 | changed=2 | errors=0",
            stdout.getvalue(),
        )
        self.assertIn(
            "reading: changed=2 | positive=2 | negative=0 | "
            "absolute_total=6.4000 | maximum_absolute=3.2000",
            stdout.getvalue(),
        )
        self.assertIn("Largest response deltas", stdout.getvalue())
        self.assertIn("reading=+3.2000", stdout.getvalue())
        self.assertIn("No response or session scores were changed", stdout.getvalue())

    def test_session_delta_report_projects_v2_without_writes(self):
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="session-delta-report",
            mock_test=self.mock_test,
            completed_at="2026-01-01T00:00:00Z",
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=self.mock_test,
            question=self.question,
            evaluated=True,
            evaluation_status="completed",
            evaluation_result=self.result,
        )
        response.apply_skill_scores()
        session.aggregate_scores()

        with tempfile.TemporaryDirectory() as directory:
            output = f"{directory}/session-deltas.csv"
            stdout = StringIO()
            call_command(
                "report_scoring_v2_session_deltas",
                "--output",
                output,
                stdout=stdout,
            )
            with open(output, encoding="utf-8") as report:
                rows = list(csv.DictReader(report))

        response.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["legacy_total"], "14.4")
        self.assertEqual(rows[0]["v2_total"], "72.0")
        self.assertEqual(rows[0]["delta_total"], "57.6")
        self.assertEqual(rows[0]["stored_session_mismatch"], "no")
        self.assertEqual(rows[0]["stored_response_legacy_mismatch"], "no")
        self.assertEqual(response.reading_score_awarded, 0.8)
        self.assertEqual(session.total_score, 14.4)
        self.assertIn("Score-changing sessions: 1", stdout.getvalue())
        self.assertIn("delta=+57.60", stdout.getvalue())
        self.assertIn("No response or session scores were changed", stdout.getvalue())

    def test_session_delta_report_uses_full_manifest_snapshot_maxima(self):
        second_question = Question.objects.create(
            mock_test_section=self.question.mock_test_section,
            subsection=self.question.subsection,
            text="Complete another blank.",
            reading_score_max=5,
        )
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="manifest-session-delta-report",
            mock_test=self.mock_test,
        )
        create_session_manifest(session.pk)
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=self.mock_test,
            question=self.question,
            evaluation_result=self.result,
        )
        response.apply_skill_scores()
        mark_session_question_answered(session.pk, self.question.pk, response.pk)
        complete_session_submission(session.pk)

        with tempfile.TemporaryDirectory() as directory:
            output = f"{directory}/manifest-session-deltas.csv"
            call_command(
                "report_scoring_v2_session_deltas",
                "--session",
                str(session.pk),
                "--output",
                output,
                stdout=StringIO(),
            )
            with open(output, encoding="utf-8") as report:
                row = next(csv.DictReader(report))

        session.refresh_from_db()
        self.assertEqual(session.expected_question_count, 2)
        self.assertEqual(second_question.reading_score_max, 5)
        self.assertEqual(row["maximum_reading"], "10.0")
        self.assertEqual(row["stored_response_total"], "7.2")
        self.assertEqual(row["legacy_total"], "7.2")
        self.assertEqual(row["v2_total"], "36.0")
        self.assertEqual(row["stored_session_mismatch"], "no")
        self.assertEqual(row["stored_response_legacy_mismatch"], "no")

    def test_session_delta_report_accepts_promoted_shadow_multiple_answer_score(self):
        subsection = SubSection.objects.create(
            section=self.question.subsection.section,
            name="mc_multiple",
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
            trait_skill_map={"reading": ["reading"]},
        )
        question_row = Question.objects.create(
            mock_test_section=self.question.mock_test_section,
            subsection=subsection,
            text="Choose every correct answer.",
            reading_score_max=2.5,
        )
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="multiple-answer-session-delta-report",
            mock_test=self.mock_test,
            completed_at="2026-01-01T00:00:00Z",
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=self.mock_test,
            question=question_row,
            evaluation_result={
                "ok": True,
                "evaluation": {
                    "scores": {"reading": {"score": 0.67, "max": 1}},
                    "answer_scoring": {
                        "raw_points": 2,
                        "maximum_raw_points": 3,
                    },
                },
            },
        )
        response.apply_skill_scores()
        session.aggregate_scores()

        with tempfile.TemporaryDirectory() as directory:
            output = f"{directory}/multiple-answer-session-deltas.csv"
            call_command(
                "report_scoring_v2_session_deltas",
                "--session",
                str(session.pk),
                "--output",
                output,
                stdout=StringIO(),
            )
            with open(output, encoding="utf-8") as report:
                row = next(csv.DictReader(report))

        self.assertEqual(row["stored_response_legacy_mismatch"], "no")
        self.assertEqual(row["stored_session_mismatch"], "no")
        self.assertEqual(row["legacy_total"], "24.12")
        self.assertEqual(row["v2_total"], "60.0")

    def test_session_delta_report_does_not_project_incomplete_session(self):
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="incomplete-session-delta-report",
            mock_test=self.mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=self.mock_test,
            question=self.question,
            evaluated=False,
            evaluation_status="pending",
        )

        with tempfile.TemporaryDirectory() as directory:
            output = f"{directory}/incomplete-session-deltas.csv"
            call_command(
                "report_scoring_v2_session_deltas",
                "--session",
                str(session.pk),
                "--output",
                output,
                stdout=StringIO(),
            )
            with open(output, encoding="utf-8") as report:
                row = next(csv.DictReader(report))

        self.assertEqual(row["evaluation_complete"], "no")
        self.assertEqual(row["v2_total"], "")
        self.assertEqual(row["delta_total"], "")
        self.assertEqual(row["score_changes"], "unknown")
