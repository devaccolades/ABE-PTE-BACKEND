import csv
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch

from examinor.scoring.contracts import VALID_SKILLS
from examinor.scoring.response_scores import compile_response_score_evidence
from mocktest.models import UserMockTestSession, UserResponse


class Command(BaseCommand):
    help = "Write a read-only legacy-versus-v2 session score delta report."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session",
            help="Session database ID or session_id.",
        )
        parser.add_argument(
            "--mock-test",
            help="Mock test UUID or exact title.",
        )
        parser.add_argument(
            "--output",
            default="scoring_v2_session_delta_report.csv",
        )

    def handle(self, *args, **options):
        rows = [self._row(session) for session in self._sessions(options)]
        self._write_report(options["output"], rows)

        changed = sum(row["score_changes"] == "yes" for row in rows)
        incomplete = sum(row["evaluation_complete"] == "no" for row in rows)
        compile_errors = sum(int(row["compile_error_count"]) for row in rows)
        storage_mismatches = sum(
            row["stored_session_mismatch"] == "yes" for row in rows
        )
        response_mismatches = sum(
            row["stored_response_legacy_mismatch"] == "yes" for row in rows
        )

        self.stdout.write("V2 session scoring delta report")
        self.stdout.write("===============================")
        self.stdout.write(f"Sessions checked: {len(rows)}")
        self.stdout.write(f"Score-changing sessions: {changed}")
        self.stdout.write(f"Incomplete sessions: {incomplete}")
        self.stdout.write(f"V2 compile errors: {compile_errors}")
        self.stdout.write(f"Stored session mismatches: {storage_mismatches}")
        self.stdout.write(f"Stored response mismatches: {response_mismatches}")
        self._print_delta_summary(rows)
        self.stdout.write(f"Report: {Path(options['output']).resolve()}")
        self.stdout.write("Read-only report. No response or session scores were changed.")

    def _sessions(self, options):
        responses = UserResponse.objects.select_related(
            "question__subsection",
        ).order_by("pk")
        sessions = (
            UserMockTestSession.objects.filter(userresponse__isnull=False)
            .select_related("mock_test")
            .prefetch_related(
                Prefetch(
                    "userresponse_set",
                    queryset=responses,
                    to_attr="scoring_responses",
                )
            )
            .distinct()
            .order_by("pk")
        )
        if options["session"]:
            identifier = options["session"]
            if identifier.isdigit():
                sessions = sessions.filter(pk=int(identifier))
            else:
                sessions = sessions.filter(session_id=identifier)
            if not sessions.exists():
                raise CommandError("--session did not match a session.")
        if options["mock_test"]:
            identifier = options["mock_test"]
            lookup = (
                "mock_test_id"
                if self._is_uuid(identifier)
                else "mock_test__title"
            )
            sessions = sessions.filter(**{lookup: identifier})
            if not sessions.exists():
                raise CommandError("--mock-test did not match any sessions.")
        return sessions

    def _row(self, session):
        skills = sorted(VALID_SKILLS)
        stored_response = {skill: 0.0 for skill in skills}
        legacy = {skill: 0.0 for skill in skills}
        v2 = {skill: 0.0 for skill in skills}
        maxima = {skill: 0.0 for skill in skills}
        compile_errors = []
        eligible_count = 0

        for response in session.scoring_responses:
            if not response.evaluated and response.evaluation_status != "completed":
                continue
            if not response.evaluation_result:
                compile_errors.append(
                    f"response {response.pk}: missing evaluation result"
                )
                continue
            eligible_count += 1
            for skill in skills:
                stored_response[skill] += float(
                    getattr(response, f"{skill}_score_awarded") or 0
                )
                maxima[skill] += float(
                    getattr(response.question, f"{skill}_score_max") or 0
                )
            try:
                evidence = compile_response_score_evidence(
                    response.question,
                    response.evaluation_result,
                    mode="shadow",
                )
            except (TypeError, ValueError) as exc:
                compile_errors.append(f"response {response.pk}: {exc}")
                continue
            if evidence["v2_error"] or evidence["v2"] is None:
                compile_errors.append(
                    f"response {response.pk}: "
                    f"{evidence['v2_error'] or 'missing V2 score evidence'}"
                )
                continue
            for skill in skills:
                legacy[skill] += float(
                    evidence["legacy"]["skills"].get(skill, {}).get("score", 0)
                )
                v2[skill] += float(
                    evidence["v2"]["skills"].get(skill, {}).get("score", 0)
                )

        total_responses = len(session.scoring_responses)
        evaluation_complete = bool(total_responses) and all(
            response.evaluated or response.evaluation_status == "completed"
            for response in session.scoring_responses
        )
        stored_session = {
            skill: float(getattr(session, f"{skill}_score_awarded") or 0)
            for skill in skills
        }
        stored_response_total = self._normalized_total(stored_response, maxima)
        legacy_total = self._normalized_total(legacy, maxima)
        has_projection = (
            evaluation_complete
            and not compile_errors
            and eligible_count == total_responses
            and eligible_count > 0
        )
        v2_total = self._normalized_total(v2, maxima) if has_projection else None

        row = {
            "session_id": session.pk,
            "session_reference": session.session_id,
            "mock_test": session.mock_test.title,
            "mock_test_id": str(session.mock_test_id),
            "pinned_scoring_mode": session.scoring_mode,
            "submitted": "yes" if session.completed_at else "no",
            "evaluation_complete": "yes" if evaluation_complete else "no",
            "total_responses": total_responses,
            "eligible_responses": eligible_count,
            "compile_error_count": len(compile_errors),
            "compile_errors": " | ".join(compile_errors),
            "stored_total": float(session.total_score or 0),
            "stored_response_total": stored_response_total,
            "legacy_total": legacy_total,
            "v2_total": v2_total if v2_total is not None else "",
            "delta_total": v2_total - legacy_total if v2_total is not None else "",
            "score_changes": (
                "yes"
                if v2_total is not None and abs(v2_total - legacy_total) > 1e-9
                else "no" if v2_total is not None else "unknown"
            ),
            "stored_session_mismatch": (
                "yes"
                if abs(float(session.total_score or 0) - stored_response_total) > 0.011
                or any(
                    abs(stored_session[skill] - stored_response[skill]) > 1e-9
                    for skill in skills
                )
                else "no"
            ),
            "stored_response_legacy_mismatch": (
                "unknown"
                if compile_errors
                else (
                    "yes"
                    if any(
                        abs(stored_response[skill] - legacy[skill]) > 1e-9
                        for skill in skills
                    )
                    else "no"
                )
            ),
        }
        for skill in skills:
            row[f"maximum_{skill}"] = maxima[skill]
            row[f"stored_{skill}"] = stored_session[skill]
            row[f"legacy_{skill}"] = legacy[skill]
            row[f"v2_{skill}"] = v2[skill] if has_projection else ""
            row[f"legacy_{skill}_scaled"] = self._normalized_skill(
                legacy[skill],
                maxima[skill],
            )
            row[f"v2_{skill}_scaled"] = (
                self._normalized_skill(v2[skill], maxima[skill])
                if has_projection
                else ""
            )
        return row

    def _print_delta_summary(self, rows):
        projected = [row for row in rows if row["delta_total"] != ""]
        self.stdout.write("")
        self.stdout.write("Overall score delta")
        self.stdout.write("-------------------")
        if not projected:
            self.stdout.write("None")
        else:
            deltas = [float(row["delta_total"]) for row in projected]
            self.stdout.write(f"Minimum: {min(deltas):+.2f}")
            self.stdout.write(f"Maximum: {max(deltas):+.2f}")
            self.stdout.write(f"Mean: {sum(deltas) / len(deltas):+.2f}")
            self.stdout.write(
                "Mean absolute: "
                f"{sum(abs(delta) for delta in deltas) / len(deltas):.2f}"
            )

        self.stdout.write("")
        self.stdout.write("Largest session deltas")
        self.stdout.write("----------------------")
        changed = sorted(
            (row for row in projected if row["score_changes"] == "yes"),
            key=lambda row: (-abs(float(row["delta_total"])), row["session_id"]),
        )
        if not changed:
            self.stdout.write("None")
            return
        for row in changed[:10]:
            self.stdout.write(
                f"session={row['session_id']} | mock_test={row['mock_test']} | "
                f"complete={row['evaluation_complete']} | "
                f"legacy={float(row['legacy_total']):.2f} | "
                f"v2={float(row['v2_total']):.2f} | "
                f"delta={float(row['delta_total']):+.2f}"
            )

    @staticmethod
    def _normalized_total(awarded, maxima):
        maximum = sum(maxima.values())
        if maximum <= 0:
            return 0.0
        return round(min((sum(awarded.values()) / maximum) * 90, 90), 2)

    @staticmethod
    def _normalized_skill(awarded, maximum):
        if maximum <= 0:
            return 0.0
        return round(min((awarded / maximum) * 90, 90), 2)

    @staticmethod
    def _is_uuid(value):
        try:
            uuid.UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return False
        return True

    @staticmethod
    def _write_report(output, rows):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        skills = sorted(VALID_SKILLS)
        fieldnames = [
            "session_id",
            "session_reference",
            "mock_test",
            "mock_test_id",
            "pinned_scoring_mode",
            "submitted",
            "evaluation_complete",
            "total_responses",
            "eligible_responses",
            "compile_error_count",
            "compile_errors",
            "stored_total",
            "stored_response_total",
            "legacy_total",
            "v2_total",
            "delta_total",
            "score_changes",
            "stored_session_mismatch",
            "stored_response_legacy_mismatch",
        ]
        for skill in skills:
            fieldnames.extend(
                [
                    f"maximum_{skill}",
                    f"stored_{skill}",
                    f"legacy_{skill}",
                    f"v2_{skill}",
                    f"legacy_{skill}_scaled",
                    f"v2_{skill}_scaled",
                ]
            )
        with path.open("w", newline="", encoding="utf-8") as report:
            writer = csv.DictWriter(report, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
