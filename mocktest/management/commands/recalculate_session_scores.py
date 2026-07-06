from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q

from mocktest.models import UserResponse
from mocktest.models import UserMockTestSession


class Command(BaseCommand):
    help = "Recalculate session-level scores from already evaluated responses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id",
            help="Only recalculate one UserMockTestSession.session_id.",
        )
        parser.add_argument(
            "--mock-test-id",
            help="Only recalculate sessions for a specific MockTest primary key.",
        )
        parser.add_argument(
            "--only-with-evaluated",
            action="store_true",
            help="Only include sessions that have at least one evaluated response.",
        )
        parser.add_argument(
            "--only-complete",
            action="store_true",
            help="Only include sessions where all submitted responses are evaluated.",
        )
        parser.add_argument(
            "--skip-duplicates",
            action="store_true",
            help="Skip sessions with duplicate responses for the same question.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be recalculated without saving.",
        )

    def handle(self, *args, **options):
        sessions = UserMockTestSession.objects.select_related("mock_test")

        if options["session_id"]:
            sessions = sessions.filter(session_id=options["session_id"])

        if options["mock_test_id"]:
            sessions = sessions.filter(mock_test_id=options["mock_test_id"])

        if options["only_with_evaluated"]:
            sessions = sessions.filter(userresponse__evaluated=True).distinct()

        sessions = sessions.annotate(
            response_count=Count("userresponse"),
            evaluated_response_count=Count(
                "userresponse",
                filter=Q(userresponse__evaluated=True),
            ),
            failed_response_count=Count(
                "userresponse",
                filter=Q(userresponse__evaluation_status="failed"),
            ),
        )

        if options["only_complete"]:
            sessions = sessions.filter(
                response_count__gt=0,
                response_count=F("evaluated_response_count"),
            )

        updated = 0
        for session in sessions.order_by("started_at"):
            duplicate_group_count = self._duplicate_group_count(session)
            if options["skip_duplicates"] and duplicate_group_count:
                self.stdout.write(
                    " ".join(
                        [
                            f"session={session.session_id}",
                            f"student={session.name}",
                            f"duplicate_groups={duplicate_group_count}",
                            "status=skipped_duplicate_responses",
                        ]
                    )
                )
                continue

            pending_count = session.response_count - session.evaluated_response_count
            complete_label = (
                "complete"
                if session.response_count and pending_count == 0
                else "incomplete"
            )
            self.stdout.write(
                " ".join(
                    [
                        f"session={session.session_id}",
                        f"student={session.name}",
                        f"responses={session.response_count}",
                        f"evaluated={session.evaluated_response_count}",
                        f"pending={pending_count}",
                        f"failed={session.failed_response_count}",
                        f"duplicate_groups={duplicate_group_count}",
                        f"status={complete_label}",
                    ]
                )
            )

            if not options["dry_run"]:
                session.aggregate_scores()

            updated += 1

        action = "would be recalculated" if options["dry_run"] else "recalculated"
        self.stdout.write(self.style.SUCCESS(f"{updated} sessions {action}."))

    def _duplicate_group_count(self, session):
        return (
            UserResponse.objects.filter(user_session=session)
            .values("question_id")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .count()
        )
