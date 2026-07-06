from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from mocktest.models import UserResponse
from mocktest.services.duplicate_responses import (
    duplicate_response_groups,
    recommended_keep_response,
)


class Command(BaseCommand):
    help = "Dry-run or delete duplicate UserResponse rows for the same session/question."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id",
            help="Limit cleanup to a UserMockTestSession.session_id.",
        )
        parser.add_argument(
            "--mock-test-id",
            help="Limit cleanup to a MockTest primary key.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Maximum duplicate groups to process.",
        )
        parser.add_argument(
            "--confirm-delete",
            action="store_true",
            help="Actually delete duplicate rows. Without this flag the command is dry-run only.",
        )
        parser.add_argument(
            "--recalculate",
            action="store_true",
            help="Recalculate affected session scores after confirmed deletion.",
        )

    def handle(self, *args, **options):
        if options["limit"] <= 0:
            raise CommandError("--limit must be greater than zero.")

        responses = UserResponse.objects.select_related(
            "user_session",
            "mock_test",
            "question__subsection",
        )

        if options["session_id"]:
            responses = responses.filter(user_session__session_id=options["session_id"])

        if options["mock_test_id"]:
            responses = responses.filter(mock_test_id=options["mock_test_id"])

        duplicate_groups = duplicate_response_groups(responses)
        rows = list(duplicate_groups[: options["limit"]])

        dry_run = not options["confirm_delete"]
        total_deleted = 0
        total_candidates = 0
        affected_sessions = {}

        self.stdout.write("Duplicate response cleanup")
        self.stdout.write("==========================")
        self.stdout.write(f"Mode: {'dry-run' if dry_run else 'delete'}")

        if not rows:
            self.stdout.write("No duplicate groups found.")
            return

        cleanup_plan = []

        for row in rows:
            group_responses = list(
                responses.filter(
                    user_session_id=row["user_session_id"],
                    question_id=row["question_id"],
                ).order_by("submitted_at", "id")
            )
            keep = recommended_keep_response(group_responses)
            delete_candidates = [
                response
                for response in group_responses
                if response.id != keep.id
            ]
            total_candidates += len(delete_candidates)
            affected_sessions[keep.user_session_id] = keep.user_session
            cleanup_plan.append((keep, delete_candidates))

            self.stdout.write(
                " | ".join(
                    [
                        f"session={keep.user_session.session_id}",
                        f"question={keep.question_id}",
                        f"keep_id={keep.id}",
                        "delete_ids="
                        + ",".join(str(response.id) for response in delete_candidates),
                    ]
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run only. {total_candidates} duplicate rows would be deleted."
                )
            )
            if options["recalculate"]:
                self.stdout.write(
                    f"{len(affected_sessions)} affected sessions would be recalculated."
                )
            self.stdout.write("Rerun with --confirm-delete to delete these rows.")
        else:
            with transaction.atomic():
                for _, delete_candidates in cleanup_plan:
                    deleted, _ = UserResponse.objects.filter(
                        id__in=[response.id for response in delete_candidates]
                    ).delete()
                    total_deleted += deleted

                if options["recalculate"]:
                    for session in affected_sessions.values():
                        session.aggregate_scores()

            self.stdout.write(
                self.style.SUCCESS(f"Deleted {total_deleted} duplicate rows.")
            )
            if options["recalculate"]:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Recalculated {len(affected_sessions)} affected sessions."
                    )
                )
