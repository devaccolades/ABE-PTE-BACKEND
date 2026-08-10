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
            evaluation_result=self.result,
        )

        response.apply_skill_scores()
        response.refresh_from_db()

        evidence = response.evaluation_result["scoring_evidence"]
        self.assertEqual(response.reading_score_awarded, 0.8)
        self.assertEqual(evidence["v2"]["skills"]["reading"]["score"], 4)

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
