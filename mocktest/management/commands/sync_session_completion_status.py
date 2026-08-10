from django.core.management.base import BaseCommand

from mocktest.models import UserMockTestSession
from mocktest.services.session_finalization import (
    recalculate_session_state,
    session_is_finalizable,
)


class Command(BaseCommand):
    help = (
        "Synchronize is_completed with exam submission and response evaluation state. "
        "Dry-run unless --apply is supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the reported completion-state corrections.",
        )

    def handle(self, *args, **options):
        changes = []
        sessions = UserMockTestSession.objects.order_by("started_at")
        for session in sessions:
            should_be_completed = (
                session_is_finalizable(session.pk)
                if session.manifest_version
                else bool(
                    session.completed_at and session.evaluations_are_complete()
                )
            )
            if session.is_completed != should_be_completed:
                changes.append((session, should_be_completed))
                self.stdout.write(
                    f"session={session.session_id} "
                    f"is_completed={session.is_completed} -> {should_be_completed}"
                )

        self.stdout.write(f"Sessions requiring correction: {len(changes)}")
        if not options["apply"]:
            self.stdout.write("Dry run only. Re-run with --apply to persist changes.")
            return

        for session, should_be_completed in changes:
            if session.manifest_version:
                recalculate_session_state(session.pk)
            else:
                session.is_completed = should_be_completed
                session.save(update_fields=["is_completed"])

        self.stdout.write(
            self.style.SUCCESS(f"Synchronized {len(changes)} session(s).")
        )
