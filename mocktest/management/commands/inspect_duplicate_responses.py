from django.core.management.base import BaseCommand

from mocktest.models import UserResponse
from mocktest.services.duplicate_responses import (
    duplicate_response_groups,
    recommended_keep_response,
)


class Command(BaseCommand):
    help = "Inspect duplicate UserResponse rows for the same session/question."

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
            "--limit",
            type=int,
            default=25,
            help="Maximum duplicate groups to list.",
        )

    def handle(self, *args, **options):
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

        total_groups = duplicate_groups.count()
        total_extra_rows = sum(row["count"] - 1 for row in duplicate_groups)

        self.stdout.write("Duplicate response inspection")
        self.stdout.write("=============================")
        self.stdout.write(f"Duplicate groups: {total_groups}")
        self.stdout.write(f"Extra duplicate rows: {total_extra_rows}")

        rows = list(duplicate_groups[: options["limit"]])
        if not rows:
            self.stdout.write("")
            self.stdout.write("None")
            return

        self.stdout.write("")
        self.stdout.write("Duplicate groups")
        self.stdout.write("----------------")

        for row in rows:
            group_responses = responses.filter(
                user_session_id=row["user_session_id"],
                question_id=row["question_id"],
            ).order_by("submitted_at", "id")
            group_responses = list(group_responses)
            first = group_responses[0]
            recommended_keep = recommended_keep_response(group_responses)
            candidate_duplicate_ids = [
                str(response.id)
                for response in group_responses
                if response.id != recommended_keep.id
            ]
            subsection = (
                first.question.subsection.name
                if first.question and first.question.subsection
                else "unknown"
            )
            self.stdout.write(
                " | ".join(
                    [
                        f"session={first.user_session.session_id}",
                        f"student={first.user_session.name}",
                        f"mock_test={first.mock_test_id}",
                        f"question={first.question_id}",
                        f"subsection={subsection}",
                        f"count={row['count']}",
                        f"recommended_keep_id={recommended_keep.id}",
                        f"candidate_duplicate_ids={','.join(candidate_duplicate_ids)}",
                        f"first={row['first_submitted_at']}",
                        f"last={row['last_submitted_at']}",
                    ]
                )
            )

            for response in group_responses:
                self.stdout.write(
                    "  "
                    + " | ".join(
                        [
                            f"id={response.id}",
                            f"evaluated={response.evaluated}",
                            f"status={response.evaluation_status}",
                            f"stage={response.evaluation_stage or '-'}",
                            f"submitted_at={response.submitted_at}",
                        ]
                    )
                )
