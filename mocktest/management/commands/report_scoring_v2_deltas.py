import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from examinor.scoring.contracts import VALID_SKILLS
from examinor.scoring.response_scores import compile_response_score_evidence
from mocktest.models import SingleResponse, UserResponse


class Command(BaseCommand):
    help = "Write a read-only legacy-versus-v2 response scoring delta report."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=("all", "user", "single"),
            default="all",
        )
        parser.add_argument("--response-id", type=int)
        parser.add_argument(
            "--session",
            help="User session database ID or session_id.",
        )
        parser.add_argument(
            "--mock-test",
            help="Mock test UUID or exact title.",
        )
        parser.add_argument("--subsection")
        parser.add_argument(
            "--output",
            default="scoring_v2_delta_report.csv",
        )

    def handle(self, *args, **options):
        if options["session"] and options["model"] == "single":
            raise CommandError("--session cannot be used with --model single.")

        rows = []
        models = []
        if options["model"] in {"all", "user"}:
            models.append(("UserResponse", self._user_responses(options)))
        if options["model"] in {"all", "single"}:
            models.append(("SingleResponse", self._single_responses(options)))

        checked = 0
        changed = 0
        compile_errors = 0
        stored_mismatches = 0
        for model_name, responses in models:
            for response in responses.iterator(chunk_size=500):
                checked += 1
                row = self._row(model_name, response)
                rows.append(row)
                if row["v2_error"]:
                    compile_errors += 1
                elif row["score_changes"] == "yes":
                    changed += 1
                if row["stored_legacy_mismatch"] == "yes":
                    stored_mismatches += 1

        self._write_report(options["output"], rows)
        self.stdout.write("V2 scoring delta report")
        self.stdout.write("=======================")
        self.stdout.write(f"Responses checked: {checked}")
        self.stdout.write(f"Score-changing responses: {changed}")
        self.stdout.write(f"V2 compile errors: {compile_errors}")
        self.stdout.write(f"Stored legacy mismatches: {stored_mismatches}")
        self.stdout.write(f"Report: {Path(options['output']).resolve()}")
        self.stdout.write("Read-only report. No response or session scores were changed.")

    def _user_responses(self, options):
        responses = UserResponse.objects.filter(
            evaluated=True,
            evaluation_result__isnull=False,
        ).select_related(
            "question__subsection",
            "user_session",
            "mock_test",
        ).order_by("pk")
        if options["response_id"]:
            responses = responses.filter(pk=options["response_id"])
        if options["session"]:
            session = options["session"]
            if session.isdigit():
                responses = responses.filter(user_session_id=int(session))
            else:
                responses = responses.filter(user_session__session_id=session)
        if options["mock_test"]:
            identifier = options["mock_test"]
            if self._is_uuid(identifier):
                responses = responses.filter(mock_test_id=identifier)
            else:
                responses = responses.filter(mock_test__title=identifier)
        if options["subsection"]:
            responses = responses.filter(question__subsection__name=options["subsection"])
        return responses

    def _single_responses(self, options):
        responses = SingleResponse.objects.filter(
            evaluated=True,
            evaluation_result__isnull=False,
        ).select_related(
            "question__subsection",
            "question__mock_test_section__mock_test",
        ).order_by("pk")
        if options["response_id"]:
            responses = responses.filter(pk=options["response_id"])
        if options["mock_test"]:
            identifier = options["mock_test"]
            prefix = "question__mock_test_section__mock_test"
            lookup = f"{prefix}_id" if self._is_uuid(identifier) else f"{prefix}__title"
            responses = responses.filter(**{lookup: identifier})
        if options["subsection"]:
            responses = responses.filter(question__subsection__name=options["subsection"])
        return responses

    def _row(self, model_name, response):
        session = getattr(response, "user_session", None)
        mock_test = getattr(response, "mock_test", None)
        if mock_test is None and response.question.mock_test_section:
            mock_test = response.question.mock_test_section.mock_test

        stored = {
            skill: float(getattr(response, f"{skill}_score_awarded") or 0)
            for skill in VALID_SKILLS
        }
        base = {
            "model": model_name,
            "response_id": response.pk,
            "session_id": session.pk if session else "",
            "session_reference": session.session_id if session else "",
            "mock_test": mock_test.title if mock_test else "",
            "mock_test_id": str(mock_test.pk) if mock_test else "",
            "question_id": response.question_id,
            "subsection": response.question.subsection.name,
            "v2_error": "",
        }
        try:
            evidence = compile_response_score_evidence(
                response.question,
                response.evaluation_result,
                mode="shadow",
            )
        except (TypeError, ValueError) as exc:
            return {
                **base,
                **self._empty_score_columns(stored),
                "score_changes": "unknown",
                "stored_legacy_mismatch": "unknown",
                "v2_error": str(exc),
            }

        legacy = {
            skill: float(evidence["legacy"]["skills"][skill]["score"])
            for skill in VALID_SKILLS
        }
        v2 = (
            {
                skill: float(evidence["v2"]["skills"].get(skill, {}).get("score", 0))
                for skill in VALID_SKILLS
            }
            if evidence["v2"]
            else None
        )
        columns = {}
        for skill in sorted(VALID_SKILLS):
            columns[f"stored_{skill}"] = stored[skill]
            columns[f"legacy_{skill}"] = legacy[skill]
            columns[f"v2_{skill}"] = v2[skill] if v2 else ""
            columns[f"delta_{skill}"] = v2[skill] - legacy[skill] if v2 else ""

        return {
            **base,
            **columns,
            "score_changes": (
                "yes"
                if v2 and any(abs(v2[skill] - legacy[skill]) > 1e-9 for skill in VALID_SKILLS)
                else "no" if v2 else "unknown"
            ),
            "stored_legacy_mismatch": (
                "yes"
                if any(abs(stored[skill] - legacy[skill]) > 1e-9 for skill in VALID_SKILLS)
                else "no"
            ),
            "v2_error": evidence["v2_error"],
        }

    @staticmethod
    def _empty_score_columns(stored):
        columns = {}
        for skill in sorted(VALID_SKILLS):
            columns[f"stored_{skill}"] = stored[skill]
            columns[f"legacy_{skill}"] = ""
            columns[f"v2_{skill}"] = ""
            columns[f"delta_{skill}"] = ""
        return columns

    @staticmethod
    def _is_uuid(value):
        import uuid

        try:
            uuid.UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return False
        return True

    def _write_report(self, output, rows):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "model",
            "response_id",
            "session_id",
            "session_reference",
            "mock_test",
            "mock_test_id",
            "question_id",
            "subsection",
        ]
        for skill in sorted(VALID_SKILLS):
            fieldnames.extend(
                [
                    f"stored_{skill}",
                    f"legacy_{skill}",
                    f"v2_{skill}",
                    f"delta_{skill}",
                ]
            )
        fieldnames.extend(
            ["score_changes", "stored_legacy_mismatch", "v2_error"]
        )
        with path.open("w", newline="", encoding="utf-8") as report:
            writer = csv.DictWriter(report, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
