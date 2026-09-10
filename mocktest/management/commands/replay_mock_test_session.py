import copy
import uuid
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from examinor.scoring.task_contracts import (
    EvaluationEngine,
    PayloadStatus,
    get_task_contract,
    inspect_answer_payload,
)
from mocktest.models import SessionQuestion, UserMockTestSession, UserResponse
from mocktest.services.evaluation_jobs import response_type_for
from mocktest.services.evaluation_queue import (
    EvaluationQueueUnavailable,
    dispatch_prepared_evaluation,
    prepare_response_evaluation,
)
from mocktest.services.session_finalization import (
    complete_session_submission,
    create_session_manifest,
)


class Command(BaseCommand):
    help = (
        "Create a fresh QA session from a completed session's stored answers and "
        "audio, then queue normal evaluations. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument("--source-session", type=int, required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--confirm", action="store_true")
        parser.add_argument("--expected-response-count", type=int)
        parser.add_argument("--expected-audio-count", type=int)
        parser.add_argument("--expected-source-result-version", type=int)

    def handle(self, *args, **options):
        self._validate_options(options)
        source, responses, summary = self._inspect_source(
            options["source_session"],
            target_name=options["name"],
            lock=False,
        )
        self._report(source, summary, options["name"])

        if not options["confirm"]:
            self.stdout.write(
                "Dry run only. No session, response, audio, or evaluation job "
                "was created."
            )
            return

        self._check_expectations(source, summary, options)
        copied_audio = []
        try:
            with transaction.atomic():
                source, responses, summary = self._inspect_source(
                    options["source_session"],
                    target_name=options["name"],
                    lock=True,
                )
                self._check_expectations(source, summary, options)
                target, dispatches = self._create_replay(
                    source,
                    responses,
                    options["name"],
                    copied_audio,
                )
        except Exception:
            self._delete_copied_audio(copied_audio)
            raise

        dispatched = 0
        delayed = 0
        for response, job, event in dispatches:
            try:
                dispatch_prepared_evaluation(response, job, event)
            except EvaluationQueueUnavailable:
                delayed += 1
            else:
                dispatched += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created QA replay session {target.pk} ({target.session_id}) with "
                f"{len(dispatches)} response(s): {dispatched} dispatched, "
                f"{delayed} saved for automatic dispatch retry."
            )
        )
        self.stdout.write(
            "Fresh evaluation is asynchronous. The original session was not changed."
        )

    @staticmethod
    def _validate_options(options):
        name = str(options["name"] or "").strip()
        if not name:
            raise CommandError("--name cannot be empty.")
        if len(name) > 255:
            raise CommandError("--name cannot exceed 255 characters.")
        options["name"] = name
        expected_names = (
            "expected_response_count",
            "expected_audio_count",
            "expected_source_result_version",
        )
        for option_name in expected_names:
            value = options[option_name]
            if value is not None and value < 0:
                raise CommandError(
                    f"--{option_name.replace('_', '-')} cannot be negative."
                )
        if options["confirm"] and any(
            options[option_name] is None for option_name in expected_names
        ):
            raise CommandError(
                "--expected-response-count, --expected-audio-count, and "
                "--expected-source-result-version are required with --confirm."
            )

    def _inspect_source(self, session_pk, *, target_name, lock):
        sessions = UserMockTestSession.objects
        if lock:
            sessions = sessions.select_for_update()
        try:
            source = sessions.get(pk=session_pk)
        except UserMockTestSession.DoesNotExist as exc:
            raise CommandError(f"Source session {session_pk} was not found.") from exc

        if not source.manifest_version:
            raise CommandError("Source session does not have an immutable manifest.")
        if not source.is_completed or not source.finalized_result_version:
            raise CommandError("Source session is not fully evaluated and finalized.")
        if not source.mock_test.is_active:
            raise CommandError("Source question paper is not active.")

        response_queryset = UserResponse.objects.filter(user_session=source)
        if lock:
            locked_ids = list(
                response_queryset.select_for_update().values_list("pk", flat=True)
            )
            response_queryset = UserResponse.objects.filter(pk__in=locked_ids)
        responses = list(
            response_queryset.order_by("question_id")
            .select_related("question__subsection")
            .prefetch_related(
                "question__options",
                "question__sub_questions__options",
            )
        )
        manifest_rows = list(
            source.question_manifest.order_by("order").values(
                "question_id_snapshot",
                "status",
                "response_id",
            )
        )
        manifest_ids = [row["question_id_snapshot"] for row in manifest_rows]
        response_by_question = {
            response.question_id: response for response in responses
        }

        errors = []
        if len(manifest_rows) != source.expected_question_count:
            errors.append(
                "Manifest count does not match the source expected-question count."
            )
        if len(response_by_question) != len(responses):
            errors.append("Source session has duplicate question responses.")
        if set(manifest_ids) != set(response_by_question):
            errors.append("Source responses do not exactly cover the session manifest.")
        if any(
            row["status"] != "answered" or not row["response_id"]
            for row in manifest_rows
        ):
            errors.append(
                "Every source manifest row must contain an answered response."
            )
        if any(
            row["response_id"]
            != getattr(
                response_by_question.get(row["question_id_snapshot"]),
                "pk",
                None,
            )
            for row in manifest_rows
        ):
            errors.append("Source manifest response links are inconsistent.")

        audio_count = 0
        ai_count = 0
        rule_count = 0
        ordered_responses = []
        for question_id in manifest_ids:
            response = response_by_question.get(question_id)
            if response is None:
                continue
            ordered_responses.append(response)
            if not response.evaluated or response.evaluation_status != "completed":
                errors.append(f"Response {response.pk} is not fully evaluated.")

            contract = get_task_contract(response.question.subsection.name)
            if contract.evaluation_engine == EvaluationEngine.AI:
                ai_count += 1
            else:
                rule_count += 1

            has_audio = bool(response.answer_audio and response.answer_audio.name)
            inspection = inspect_answer_payload(
                response.question.subsection.name,
                response.answer_data,
                has_audio=has_audio,
            )
            if inspection.status == PayloadStatus.INVALID:
                errors.append(f"Response {response.pk} has an invalid answer payload.")

            if contract.requires_response_audio:
                audio_count += 1
                if not has_audio:
                    errors.append(f"Response {response.pk} has no stored audio name.")
                    continue
                storage = response.answer_audio.storage
                name = response.answer_audio.name
                try:
                    exists = storage.exists(name)
                    size = response.answer_audio.size if exists else 0
                except (FileNotFoundError, OSError) as exc:
                    errors.append(
                        f"Response {response.pk} audio cannot be read: {exc}."
                    )
                    continue
                if not exists or not size:
                    errors.append(
                        f"Response {response.pk} audio file is missing or empty."
                    )

        if errors:
            for error in errors:
                self.stderr.write(error)
            raise CommandError("QA replay validation failed; no changes were made.")

        if UserMockTestSession.objects.filter(
            mock_test=source.mock_test,
            name=target_name,
        ).exists():
            raise CommandError(
                "A session with this QA replay name already exists for the paper."
            )

        return source, ordered_responses, {
            "responses": len(ordered_responses),
            "audio": audio_count,
            "text": len(ordered_responses) - audio_count,
            "ai": ai_count,
            "rule": rule_count,
        }

    def _report(self, source, summary, name):
        self.stdout.write("Mock-test QA replay")
        self.stdout.write("===================")
        self.stdout.write(
            f"Source: {source.pk} ({source.session_id}) | candidate={source.name}"
        )
        self.stdout.write(f"Question paper: {source.mock_test.title}")
        self.stdout.write(f"Source scoring mode: {source.scoring_mode}")
        self.stdout.write(f"Replay scoring mode: {source.mock_test.scoring_mode}")
        self.stdout.write(f"Source result version: {source.finalized_result_version}")
        self.stdout.write(f"Replay name: {name}")
        self.stdout.write(f"Responses: {summary['responses']}")
        self.stdout.write(
            f"Inputs: audio={summary['audio']} | text={summary['text']}"
        )
        self.stdout.write(
            f"Evaluation engines: ai={summary['ai']} | rule={summary['rule']}"
        )

    @staticmethod
    def _check_expectations(source, summary, options):
        expected = {
            "responses": options["expected_response_count"],
            "audio": options["expected_audio_count"],
            "result version": options["expected_source_result_version"],
        }
        actual = {
            "responses": summary["responses"],
            "audio": summary["audio"],
            "result version": source.finalized_result_version,
        }
        mismatches = [
            f"{label}: expected {expected[label]}, found {actual[label]}"
            for label in expected
            if expected[label] != actual[label]
        ]
        if mismatches:
            raise CommandError(
                "Replay expectations changed (" + "; ".join(mismatches) + ")."
            )

    def _create_replay(self, source, responses, name, copied_audio):
        target = UserMockTestSession.objects.create(
            name=name,
            session_id=str(uuid.uuid4()),
            mock_test=source.mock_test,
            scoring_mode=source.mock_test.scoring_mode,
        )
        create_session_manifest(target.pk)
        target.refresh_from_db()
        target.mock_test_snapshot = {
            **target.mock_test_snapshot,
            "qa_replay": {
                "source_session_pk": source.pk,
                "source_session_id": source.session_id,
                "source_result_version": source.finalized_result_version,
            },
        }
        target.save(update_fields=["mock_test_snapshot"])

        target_manifest_ids = list(
            target.question_manifest.order_by("order").values_list(
                "question_id_snapshot",
                flat=True,
            )
        )
        source_question_ids = [response.question_id for response in responses]
        if target_manifest_ids != source_question_ids:
            raise CommandError(
                "The current question-paper manifest differs from the source session."
            )

        now = timezone.now()
        replay_responses = []
        for source_response in responses:
            replay = UserResponse(
                user_session=target,
                mock_test=target.mock_test,
                question=source_response.question,
                answer_data=copy.deepcopy(source_response.answer_data),
                transcribed_audio_data=None,
            )
            if source_response.answer_audio and source_response.answer_audio.name:
                storage = source_response.answer_audio.storage
                source_name = Path(source_response.answer_audio.name).name
                replay_name = (
                    f"qa-replay-{target.session_id}-{source_response.question_id}-"
                    f"{source_name}"
                )
                with storage.open(source_response.answer_audio.name, "rb") as handle:
                    replay.answer_audio.save(
                        replay_name,
                        File(handle),
                        save=False,
                    )
                copied_audio.append(
                    (replay.answer_audio.storage, replay.answer_audio.name)
                )
            replay.save()
            updated = SessionQuestion.objects.filter(
                session=target,
                question_id_snapshot=replay.question_id,
                status="pending",
            ).update(
                status="answered",
                response=replay,
                resolved_at=now,
            )
            if updated != 1:
                raise CommandError(
                    f"Could not resolve replay manifest question {replay.question_id}."
                )
            replay_responses.append(replay)

        complete_session_submission(target.pk)
        dispatches = []
        for replay in replay_responses:
            job, event = prepare_response_evaluation(replay)
            if response_type_for(replay) != "user":
                raise CommandError("Replay created an unexpected response type.")
            dispatches.append((replay, job, event))
        return target, dispatches

    @staticmethod
    def _delete_copied_audio(copied_audio):
        for storage, name in copied_audio:
            try:
                storage.delete(name)
            except OSError:
                pass
