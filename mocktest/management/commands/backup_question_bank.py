import json
import shutil
from pathlib import Path

from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand
from django.utils import timezone

from mocktest.models import (
    GlobalRubric,
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    Section,
    SubQuestion,
    SubSection,
)


QUESTION_BANK_MODELS = [
    Section,
    MockTest,
    MockTestSection,
    GlobalRubric,
    SubSection,
    Question,
    SubQuestion,
    QuestionOption,
]


class Command(BaseCommand):
    help = "Back up mock-test question-bank/master data without user responses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=None,
            help="Directory where the backup folder should be created.",
        )
        parser.add_argument(
            "--skip-media",
            action="store_true",
            help="Do not copy question audio/image files.",
        )

    def handle(self, *args, **options):
        timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        base_dir = Path(options["output_dir"] or settings.BASE_DIR / "backups" / "question_bank")
        backup_dir = base_dir / timestamp
        backup_dir.mkdir(parents=True, exist_ok=False)

        objects = []
        counts = {}
        for model in QUESTION_BANK_MODELS:
            queryset = model.objects.all().order_by("pk")
            counts[model._meta.label] = queryset.count()
            objects.extend(queryset)

        data_path = backup_dir / "question_bank.json"
        data_path.write_text(
            serializers.serialize("json", objects, indent=2),
            encoding="utf-8",
        )

        copied_media = []
        missing_media = []
        if not options["skip_media"]:
            copied_media, missing_media = self._copy_question_media(backup_dir)

        manifest = {
            "created_at": timezone.localtime().isoformat(),
            "format": "django-json-fixture",
            "fixture": str(data_path.name),
            "excluded": [
                "UserMockTestSession",
                "UserResponse",
                "SingleResponse",
                "response audio files",
            ],
            "counts": counts,
            "media_files_copied": copied_media,
            "media_files_missing": missing_media,
            "restore_hint": "Run: python manage.py loaddata question_bank.json, then copy media/ contents back under MEDIA_ROOT.",
        }
        (backup_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        self.stdout.write(self.style.SUCCESS(f"Question bank backup created: {backup_dir}"))
        self.stdout.write(f"Fixture: {data_path}")
        if options["skip_media"]:
            self.stdout.write("Media copy skipped.")
        else:
            self.stdout.write(f"Media copied: {len(copied_media)}")
            if missing_media:
                self.stdout.write(self.style.WARNING(f"Missing media files: {len(missing_media)}"))

    def _copy_question_media(self, backup_dir):
        media_root = Path(settings.MEDIA_ROOT)
        backup_media_root = backup_dir / "media"
        copied = []
        missing = []

        for question in Question.objects.exclude(audio="").exclude(audio__isnull=True):
            self._copy_file_field(question.audio.name, media_root, backup_media_root, copied, missing)

        for question in Question.objects.exclude(image="").exclude(image__isnull=True):
            self._copy_file_field(question.image.name, media_root, backup_media_root, copied, missing)

        return copied, missing

    def _copy_file_field(self, relative_name, media_root, backup_media_root, copied, missing):
        source = media_root / relative_name
        destination = backup_media_root / relative_name

        if not source.exists():
            missing.append(relative_name)
            return

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relative_name)
