import csv
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from examinor.scoring.task_contracts import (
    PayloadStatus,
    TaskContractError,
    has_usable_transcript,
    inspect_answer_payload,
)
from mocktest.models import SingleResponse, UserResponse


class Command(BaseCommand):
    help = (
        "Audit stored response payloads against subsection contracts without "
        "changing responses or evaluation results."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=("all", "user", "single"),
            default="all",
            help="Response model to audit (default: all).",
        )
        parser.add_argument(
            "--detail-limit",
            type=int,
            default=50,
            help="Maximum invalid/legacy rows printed to stdout (default: 50).",
        )
        parser.add_argument(
            "--output",
            help="Optional privacy-safe CSV path; answer content is never exported.",
        )
        parser.add_argument(
            "--fail-on-invalid",
            action="store_true",
            help="Exit non-zero when one or more invalid stored payloads are found.",
        )

    def handle(self, *args, **options):
        if options["detail_limit"] < 0:
            raise CommandError("--detail-limit cannot be negative.")

        model_choice = options["model"]
        models = []
        if model_choice in {"all", "user"}:
            models.append(UserResponse)
        if model_choice in {"all", "single"}:
            models.append(SingleResponse)

        rows = []
        status_counts = Counter()
        subsection_counts = Counter()
        issue_counts = Counter()

        for model in models:
            queryset = (
                model.objects.select_related("question__subsection")
                .only(
                    "id",
                    "question_id",
                    "question__subsection__name",
                    "answer_data",
                    "answer_audio",
                    "transcribed_audio_data",
                    "evaluation_status",
                )
                .order_by("id")
            )
            for response in queryset.iterator(chunk_size=500):
                subsection = response.question.subsection.name
                has_transcript = has_usable_transcript(
                    response.transcribed_audio_data
                )
                try:
                    inspection = inspect_answer_payload(
                        subsection,
                        response.answer_data,
                        has_audio=bool(
                            response.answer_audio and response.answer_audio.name
                        ),
                        has_transcript=has_transcript,
                    )
                except TaskContractError as exc:
                    raise CommandError(str(exc)) from exc

                model_name = model.__name__
                issue_codes = tuple(issue.code for issue in inspection.issues)
                row = {
                    "model": model_name,
                    "response_id": response.pk,
                    "question_id": response.question_id,
                    "subsection": subsection,
                    "payload_status": inspection.status.value,
                    "issue_codes": ",".join(issue_codes),
                    "has_audio": bool(
                        response.answer_audio and response.answer_audio.name
                    ),
                    "has_transcript": has_transcript,
                    "evaluation_status": response.evaluation_status,
                }
                rows.append(row)
                status_counts[(model_name, inspection.status.value)] += 1
                subsection_counts[(subsection, inspection.status.value)] += 1
                for issue_code in issue_codes:
                    issue_counts[issue_code] += 1

        self.stdout.write("Answer payload contract audit")
        self.stdout.write("=============================")
        self.stdout.write(f"Responses checked: {len(rows)}")
        for model in models:
            model_name = model.__name__
            total = sum(
                count
                for (counted_model, _status), count in status_counts.items()
                if counted_model == model_name
            )
            self.stdout.write(f"{model_name}: {total}")
            for status in PayloadStatus:
                self.stdout.write(
                    f"  {status.value}: {status_counts[(model_name, status.value)]}"
                )

        self.stdout.write("")
        self.stdout.write("By subsection")
        self.stdout.write("-------------")
        for subsection in sorted({key[0] for key in subsection_counts}):
            counts = ", ".join(
                f"{status.value}={subsection_counts[(subsection, status.value)]}"
                for status in PayloadStatus
            )
            self.stdout.write(f"{subsection}: {counts}")

        if issue_counts:
            self.stdout.write("")
            self.stdout.write("Issue counts")
            self.stdout.write("------------")
            for issue_code, count in sorted(issue_counts.items()):
                self.stdout.write(f"{issue_code}: {count}")

        detail_rows = [
            row
            for row in rows
            if row["payload_status"] != PayloadStatus.CANONICAL.value
        ][: options["detail_limit"]]
        if detail_rows:
            self.stdout.write("")
            self.stdout.write("Legacy/invalid response IDs")
            self.stdout.write("---------------------------")
            for row in detail_rows:
                self.stdout.write(
                    "{payload_status} | model={model} | response={response_id} | "
                    "question={question_id} | subsection={subsection} | "
                    "issues={issue_codes}".format(**row)
                )

        if options["output"]:
            self._write_csv(Path(options["output"]), rows)

        invalid_count = sum(
            count
            for (_model, status), count in status_counts.items()
            if status == PayloadStatus.INVALID.value
        )
        if options["fail_on_invalid"] and invalid_count:
            raise CommandError(
                f"Answer payload audit found {invalid_count} invalid response(s)."
            )

    def _write_csv(self, output_path, rows):
        if not output_path.parent.exists():
            raise CommandError(
                f"Output directory does not exist: {output_path.parent}"
            )
        fieldnames = (
            "model",
            "response_id",
            "question_id",
            "subsection",
            "payload_status",
            "issue_codes",
            "has_audio",
            "has_transcript",
            "evaluation_status",
        )
        with output_path.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        self.stdout.write(f"Report: {output_path.resolve()}")
