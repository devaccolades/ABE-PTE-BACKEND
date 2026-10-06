from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mocktest.models import AnswerTemplate
from mocktest.services.known_answer_template_catalog import (
    EXPERT_ANSWER_TEMPLATES,
)


class Command(BaseCommand):
    help = "Load the reviewed known-answer templates used by the integrity gate."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Create or update the reviewed templates.",
        )
        parser.add_argument(
            "--expected-count",
            type=int,
            help="Abort unless the reviewed catalog contains this many templates.",
        )

    def handle(self, *args, **options):
        templates = EXPERT_ANSWER_TEMPLATES
        expected_count = options.get("expected_count")
        if expected_count is not None and expected_count != len(templates):
            raise CommandError(
                f"Expected {expected_count} template(s), found {len(templates)}."
            )

        self.stdout.write("Known answer template loader")
        self.stdout.write("============================")
        for template in templates:
            self.stdout.write(
                f"{template['answer_type']} | {template['name']} | "
                f"version={template['version']}"
            )
        self.stdout.write(f"Templates in reviewed catalog: {len(templates)}")

        if not options["confirm"]:
            self.stdout.write(
                "Dry run only. No answer template records were changed."
            )
            return

        created = 0
        updated = 0
        with transaction.atomic():
            for template in templates:
                defaults = {
                    key: value
                    for key, value in template.items()
                    if key not in {"name", "version"}
                }
                _, was_created = AnswerTemplate.objects.update_or_create(
                    name=template["name"],
                    version=template["version"],
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(templates)} reviewed template(s): "
                f"{created} created, {updated} updated."
            )
        )
