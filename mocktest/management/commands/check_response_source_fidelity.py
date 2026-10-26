import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from examinor.services.prompt_builder import evaluation_answer_text
from examinor.services.source_fidelity import audit_source_fidelity, fidelity_enabled
from mocktest.models import SingleResponse, UserResponse


class Command(BaseCommand):
    help = "Inspect summary source fidelity without updating responses, scores, jobs or caches."

    def add_arguments(self, parser):
        parser.add_argument("--response-id", type=int, required=True)
        parser.add_argument("--response-model", choices=("single", "user"), default="single")
        parser.add_argument("--evaluate", action="store_true",
                            help="Make a paid provider review, without saving its result or cache.")

    def handle(self, *args, **options):
        model = SingleResponse if options["response_model"] == "single" else UserResponse
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
            try:
                response = model.objects.select_related("question__subsection").get(pk=options["response_id"])
            except model.DoesNotExist as exc:
                raise CommandError("Response not found.") from exc
            question = response.question
            task = question.subsection.name if question.subsection else ""
            if not fidelity_enabled(task):
                raise CommandError("Source fidelity is disabled or not applicable to this task.")
            answer = evaluation_answer_text({"answer_data": response.answer_data,
                                             "transcribed_audio_data": response.transcribed_audio_data})
            source = (question.text if task == "summarize_written_text" else question.correct_answer) or ""
        # The provider call is outside the transaction; use_cache=False forbids cache writes.
        if not answer.strip() or not source.strip():
            raise CommandError("Both candidate answer and source text are required.")
        self.stdout.write(f"Response: {model.__name__} {response.pk}")
        self.stdout.write(f"Question: {question.pk} ({question.name}); task={task}")
        self.stdout.write(f"Current model: {settings.OPENAI_EVALUATION_MODEL}")
        self.stdout.write("Uses current source and stored text; does not retranscribe or recover the historical prompt.")
        if options["evaluate"]:
            result = audit_source_fidelity(task, answer, source, use_cache=False)
            self.stdout.write(json.dumps(result, indent=2, ensure_ascii=False))
            if result["status"] == "unavailable":
                raise CommandError(result["reason"])
        else:
            self.stdout.write("Dry run. No provider was called. Add --evaluate for a paid non-saving review.")
        self.stdout.write("No response, score, job or cache was changed.")
