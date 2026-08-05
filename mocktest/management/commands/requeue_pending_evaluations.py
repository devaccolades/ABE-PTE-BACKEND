from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from examinor.scoring.task_contracts import has_usable_transcript
from mocktest.models import SingleResponse, UserResponse
from mocktest.services.evaluation_input import (
    question_requires_audio,
    response_input_issue,
)
from mocktest.services.evaluation_queue import (
    EvaluationQueueUnavailable,
    queue_response_evaluation,
)


class Command(BaseCommand):
    help = "Queue unevaluated responses for Celery evaluation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id",
            help="Only queue responses for a specific UserMockTestSession.session_id.",
        )
        parser.add_argument(
            "--mock-test-id",
            help="Only queue responses for a specific MockTest primary key.",
        )
        parser.add_argument(
            "--response-id",
            type=int,
            help="Only queue one response by id.",
        )
        parser.add_argument(
            "--question-id",
            type=int,
            help="Only queue responses for a specific Question primary key.",
        )
        parser.add_argument(
            "--single",
            action="store_true",
            help="Queue SingleResponse rows instead of UserResponse rows.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of responses to queue.",
        )
        parser.add_argument(
            "--status",
            choices=["pending", "transcribing", "evaluating", "completed", "failed"],
            help="Only queue responses with this evaluation_status.",
        )
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            help=(
                "Only queue responses whose last evaluation attempt, or submitted_at "
                "when no attempt exists, is older than this many minutes."
            ),
        )
        parser.add_argument(
            "--include-evaluated",
            action="store_true",
            help="Allow requeueing already evaluated responses. Use carefully.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be queued without sending Celery tasks.",
        )

    def handle(self, *args, **options):
        if options["single"] and (options["session_id"] or options["mock_test_id"]):
            raise CommandError("--session-id and --mock-test-id are only valid for UserResponse.")
        if (
            options["older_than_minutes"] is not None
            and options["older_than_minutes"] < 0
        ):
            raise CommandError("--older-than-minutes must be zero or greater.")

        if options["single"]:
            responses = SingleResponse.objects.select_related("question__subsection")
        else:
            responses = UserResponse.objects.select_related(
                "question__subsection",
                "user_session",
                "mock_test",
            )

        if not options["include_evaluated"]:
            responses = responses.filter(evaluated=False)

        if options["session_id"] and not options["single"]:
            responses = responses.filter(user_session__session_id=options["session_id"])

        if options["mock_test_id"] and not options["single"]:
            responses = responses.filter(mock_test_id=options["mock_test_id"])

        if options["response_id"]:
            responses = responses.filter(id=options["response_id"])

        if options["question_id"]:
            responses = responses.filter(question_id=options["question_id"])

        if options["status"]:
            responses = responses.filter(evaluation_status=options["status"])

        if options["older_than_minutes"] is not None:
            cutoff = timezone.now() - timezone.timedelta(
                minutes=options["older_than_minutes"]
            )
            responses = responses.filter(
                Q(last_evaluation_attempt_at__lte=cutoff)
                | Q(last_evaluation_attempt_at__isnull=True, submitted_at__lte=cutoff)
            )

        responses = responses.order_by("submitted_at")

        if options["limit"]:
            responses = responses[: options["limit"]]

        queued = 0
        queue_failures = 0
        non_retryable = 0
        by_mode = {}

        for response in responses:
            if response_input_issue(response):
                non_retryable += 1
                continue
            try:
                mode = self._queue_or_preview(response, options["dry_run"])
            except EvaluationQueueUnavailable:
                queue_failures += 1
                continue
            by_mode[mode] = by_mode.get(mode, 0) + 1
            queued += 1

        action = "would be queued" if options["dry_run"] else "queued"
        self.stdout.write(self.style.SUCCESS(f"{queued} responses {action}."))

        for mode, count in sorted(by_mode.items()):
            self.stdout.write(f"{mode}: {count}")

        if queue_failures:
            self.stderr.write(
                self.style.ERROR(
                    f"{queue_failures} response(s) could not be queued and were marked failed."
                )
            )
        if non_retryable:
            self.stderr.write(
                self.style.WARNING(
                    f"{non_retryable} response(s) skipped because required "
                    "evaluation input is missing."
                )
            )

    def _queue_or_preview(self, response, dry_run):
        needs_transcription = (
            question_requires_audio(response.question)
            and response.answer_audio
            and not has_usable_transcript(response.transcribed_audio_data)
        )

        mode = "transcription_and_evaluation" if needs_transcription else "evaluation"

        if not dry_run:
            queue_response_evaluation(response)

        return mode
