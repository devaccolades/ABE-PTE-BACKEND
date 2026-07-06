from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q
from django.utils import timezone

from mocktest.models import SingleResponse, UserMockTestSession, UserResponse


class Command(BaseCommand):
    help = "Inspect response evaluation state without changing data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id",
            help="Limit inspection to a UserMockTestSession.session_id.",
        )
        parser.add_argument(
            "--mock-test-id",
            help="Limit inspection to a MockTest primary key.",
        )
        parser.add_argument(
            "--single",
            action="store_true",
            help="Inspect SingleResponse rows instead of UserResponse rows.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Maximum pending responses to list.",
        )
        parser.add_argument(
            "--status",
            choices=["pending", "transcribing", "evaluating", "completed", "failed"],
            help="Limit inspection to one evaluation_status.",
        )
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            help=(
                "Only inspect responses whose last evaluation attempt, or submitted_at "
                "when no attempt exists, is older than this many minutes."
            ),
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
                "user_session",
                "mock_test",
                "question__subsection",
            )

        if options["session_id"] and not options["single"]:
            responses = responses.filter(user_session__session_id=options["session_id"])

        if options["mock_test_id"] and not options["single"]:
            responses = responses.filter(mock_test_id=options["mock_test_id"])

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

        total = responses.count()
        evaluated = responses.filter(evaluated=True).count()
        pending = responses.filter(evaluated=False).count()
        audio_pending_transcription = responses.filter(
            evaluated=False,
            answer_audio__isnull=False,
            transcribed_audio_data__isnull=True,
        ).exclude(answer_audio="").count()
        pending_with_transcription = responses.filter(
            evaluated=False,
            transcribed_audio_data__isnull=False,
        ).count()
        pending_with_result = responses.filter(
            evaluated=False,
        ).exclude(
            Q(evaluation_result={}) | Q(evaluation_result__isnull=True)
        ).count()
        failed = responses.filter(evaluation_status="failed").count()
        transcribing = responses.filter(evaluation_status="transcribing").count()
        evaluating_status = responses.filter(evaluation_status="evaluating").count()

        sessions_with_pending = None
        if not options["single"]:
            sessions_with_pending = UserMockTestSession.objects.filter(
                userresponse__in=responses.filter(evaluated=False),
            ).distinct().count()

        self.stdout.write("Evaluation inspection")
        self.stdout.write("=====================")
        self.stdout.write(f"Total responses: {total}")
        self.stdout.write(f"Evaluated responses: {evaluated}")
        self.stdout.write(f"Pending responses: {pending}")
        if sessions_with_pending is not None:
            self.stdout.write(f"Sessions with pending responses: {sessions_with_pending}")
        self.stdout.write(f"Audio pending transcription: {audio_pending_transcription}")
        self.stdout.write(f"Pending with transcription present: {pending_with_transcription}")
        self.stdout.write(f"Pending with evaluation_result present: {pending_with_result}")
        self.stdout.write(f"Status failed: {failed}")
        self.stdout.write(f"Status transcribing: {transcribing}")
        self.stdout.write(f"Status evaluating: {evaluating_status}")

        self._print_by_status(responses)
        self._print_by_subsection(responses)
        if options["single"]:
            self._print_single_pending_examples(responses, options["limit"])
        else:
            self._print_pending_examples(responses, options["limit"])

    def _print_by_status(self, responses):
        self.stdout.write("")
        self.stdout.write("Responses by status")
        self.stdout.write("-------------------")

        rows = (
            responses.values("evaluation_status")
            .annotate(count=Count("id"))
            .order_by("-count", "evaluation_status")
        )

        if not rows:
            self.stdout.write("None")
            return

        for row in rows:
            status = row["evaluation_status"] or "unknown"
            self.stdout.write(f"{status}: {row['count']}")

    def _print_by_subsection(self, responses):
        self.stdout.write("")
        self.stdout.write("Pending by subsection")
        self.stdout.write("---------------------")

        rows = (
            responses.filter(evaluated=False)
            .values("question__subsection__name")
            .annotate(count=Count("id"))
            .order_by("-count", "question__subsection__name")
        )

        if not rows:
            self.stdout.write("None")
            return

        for row in rows:
            subsection = row["question__subsection__name"] or "unknown"
            self.stdout.write(f"{subsection}: {row['count']}")

    def _print_pending_examples(self, responses, limit):
        self.stdout.write("")
        self.stdout.write("Pending examples")
        self.stdout.write("----------------")

        pending = (
            responses.filter(evaluated=False)
            .order_by("submitted_at")
        )[:limit]

        if not pending:
            self.stdout.write("None")
            return

        for response in pending:
            subsection = (
                response.question.subsection.name
                if response.question and response.question.subsection
                else "unknown"
            )
            has_audio = bool(response.answer_audio)
            has_transcription = response.transcribed_audio_data is not None
            has_result = bool(response.evaluation_result)
            self.stdout.write(
                " | ".join(
                    [
                        f"id={response.id}",
                        f"session={response.user_session.session_id}",
                        f"student={response.user_session.name}",
                        f"mock_test={response.mock_test_id}",
                        f"subsection={subsection}",
                        f"status={response.evaluation_status}",
                        f"stage={response.evaluation_stage or '-'}",
                        f"audio={has_audio}",
                        f"transcribed={has_transcription}",
                        f"has_result={has_result}",
                        f"error={response.evaluation_error or '-'}",
                        f"submitted_at={response.submitted_at}",
                    ]
                )
            )

    def _print_single_pending_examples(self, responses, limit):
        self.stdout.write("")
        self.stdout.write("Pending examples")
        self.stdout.write("----------------")

        pending = responses.filter(evaluated=False).order_by("submitted_at")[:limit]

        if not pending:
            self.stdout.write("None")
            return

        for response in pending:
            subsection = (
                response.question.subsection.name
                if response.question and response.question.subsection
                else "unknown"
            )
            has_audio = bool(response.answer_audio)
            has_transcription = response.transcribed_audio_data is not None
            has_result = bool(response.evaluation_result)
            self.stdout.write(
                " | ".join(
                    [
                        f"id={response.id}",
                        f"student={response.name}",
                        f"question={response.question_id}",
                        f"subsection={subsection}",
                        f"status={response.evaluation_status}",
                        f"stage={response.evaluation_stage or '-'}",
                        f"audio={has_audio}",
                        f"transcribed={has_transcription}",
                        f"has_result={has_result}",
                        f"error={response.evaluation_error or '-'}",
                        f"submitted_at={response.submitted_at}",
                    ]
                )
            )
