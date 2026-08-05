from django.core.management.base import BaseCommand, CommandError

from examinor.scoring.task_contracts import has_usable_transcript
from mocktest.models import SingleResponse, UserResponse
from mocktest.services.evaluation_input import (
    question_requires_audio,
    response_input_issue,
)
from mocktest.tasks import (
    evaluate_single_response,
    evaluate_user_response,
    transcribe_single_task,
    transcribe_task,
)


class Command(BaseCommand):
    help = "Run transcription/evaluation for one response synchronously for diagnostics."

    def add_arguments(self, parser):
        parser.add_argument("response_id", type=int)
        parser.add_argument(
            "--single",
            action="store_true",
            help="Evaluate a SingleResponse instead of a UserResponse.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print what would run.",
        )
        parser.add_argument(
            "--force-transcription",
            action="store_true",
            help="Run transcription again when an audio file exists, even if a transcript is already saved.",
        )

    def handle(self, *args, **options):
        response = self._get_response(options["response_id"], options["single"])
        subsection = response.question.subsection

        if not subsection:
            raise CommandError(f"Question {response.question_id} has no subsection.")

        input_issue = response_input_issue(response)
        if input_issue:
            raise CommandError(f"{input_issue.code}: {input_issue.message}")

        needs_transcription = self._needs_transcription(
            response,
            options["force_transcription"],
        )

        self.stdout.write(f"Response id: {response.id}")
        self.stdout.write(f"Question id: {response.question_id}")
        self.stdout.write(f"Subsection: {subsection.name}")
        self.stdout.write(f"Evaluation type: {subsection.evaluation_type}")
        self.stdout.write(f"Current evaluated: {response.evaluated}")
        self.stdout.write(f"Current status: {response.evaluation_status}")
        self.stdout.write(f"Current stage: {response.evaluation_stage or '-'}")
        self.stdout.write(f"Current error: {response.evaluation_error or '-'}")
        self.stdout.write(f"Has audio: {bool(response.answer_audio)}")
        self.stdout.write(
            f"Has transcription: "
            f"{has_usable_transcript(response.transcribed_audio_data)}"
        )
        self.stdout.write(f"Needs transcription: {needs_transcription}")

        if options["dry_run"]:
            self.stdout.write("Dry run only. No tasks executed.")
            return

        if options["single"]:
            self._run_single(response, needs_transcription)
        else:
            self._run_user_response(response, needs_transcription)

        response.refresh_from_db()
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Evaluation command finished."))
        self.stdout.write(f"evaluated={response.evaluated}")
        self.stdout.write(f"evaluation_status={response.evaluation_status}")
        self.stdout.write(f"evaluation_stage={response.evaluation_stage or '-'}")
        self.stdout.write(f"evaluation_error={response.evaluation_error or '-'}")

    def _get_response(self, response_id, is_single):
        model = SingleResponse if is_single else UserResponse

        try:
            return model.objects.select_related("question__subsection").get(id=response_id)
        except model.DoesNotExist as exc:
            raise CommandError(f"{model.__name__} {response_id} does not exist.") from exc

    def _needs_transcription(self, response, force_transcription):
        if not question_requires_audio(response.question):
            return False

        if not response.answer_audio:
            return False

        return force_transcription or not has_usable_transcript(
            response.transcribed_audio_data
        )

    def _run_user_response(self, response, needs_transcription):
        if needs_transcription:
            transcription_result = transcribe_task.apply(args=(response.id,))
            self.stdout.write(f"transcription_task_state={transcription_result.state}")
            if transcription_result.failed():
                self.stdout.write(str(transcription_result.result))
                return

        evaluation_result = evaluate_user_response.apply(
            args=(response.id, response.question_id)
        )
        self.stdout.write(f"evaluation_task_state={evaluation_result.state}")
        self.stdout.write(str(evaluation_result.result))

    def _run_single(self, response, needs_transcription):
        if needs_transcription:
            transcription_result = transcribe_single_task.apply(args=(response.id,))
            self.stdout.write(f"transcription_task_state={transcription_result.state}")
            if transcription_result.failed():
                self.stdout.write(str(transcription_result.result))
                return

        evaluation_result = evaluate_single_response.apply(
            args=(response.id, response.question_id)
        )
        self.stdout.write(f"evaluation_task_state={evaluation_result.state}")
        self.stdout.write(str(evaluation_result.result))
