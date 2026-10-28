import contextlib
import io
import json
import logging
import os
import shutil
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections
from django.test.utils import setup_databases, teardown_databases

from examinor.models import EvaluationCache
from examinor.scoring.task_contracts import EvaluationEngine, get_task_contract
from mocktest.evaluation_cases import CASES
from mocktest.evaluation_cases.answers import build_submission
from mocktest.evaluation_cases.schema import check_expectations, observe
from mocktest.models import Question, SingleResponse
from mocktest.tasks import evaluate_single_response


def uses_ai(case):
    return get_task_contract(case.task).evaluation_engine == EvaluationEngine.AI


class Command(BaseCommand):
    help = (
        "Run the evaluation case suite through the real evaluation task, against a "
        "question-bank export loaded into a throwaway database. AI cases call OpenAI."
    )
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--bank",
            help="Question-bank export from backup_question_bank (default: question_bank.json in the project root).",
        )
        parser.add_argument("--task", action="append", default=[], help="Only run this task type (repeatable).")
        parser.add_argument("--case", action="append", default=[], help="Only run this case id (repeatable).")
        parser.add_argument("--rule-only", action="store_true", help="Skip AI cases; no OpenAI calls.")
        parser.add_argument("--repeat", type=int, default=1, help="Run every case this many times to measure stability.")
        parser.add_argument("--workers", type=int, default=4, help="Cases evaluated in parallel.")
        parser.add_argument("--report", help="Write per-run results to this JSON file.")
        parser.add_argument("--list", action="store_true", help="List the selected cases and exit.")
        parser.add_argument("--verbose", action="store_true", help="Show task output and pipeline log warnings.")

    def handle(self, *args, **options):
        cases = self._select(options)
        if options["list"]:
            for case in cases:
                engine = "ai  " if uses_ai(case) else "rule"
                self.stdout.write(f"{engine} {case.task:28} {case.id:26} {case.label}")
            self.stdout.write(f"{len(cases)} case(s)")
            return
        if options["repeat"] < 1 or options["workers"] < 1:
            raise CommandError("--repeat and --workers must be at least 1.")

        bank = Path(options["bank"] or Path(settings.BASE_DIR) / "question_bank.json")
        if not bank.is_file():
            raise CommandError(
                f"Question-bank export not found at {bank}. Export it on the server with "
                "backup_question_bank (see docs/EVALUATION_CASES.md) or pass --bank."
            )
        ai_count = sum(uses_ai(case) for case in cases)
        if ai_count and not settings.OPENAI_API_KEY:
            raise CommandError("OPENAI_API_KEY is not set. Set it or pass --rule-only.")
        self.stdout.write(
            f"Running {len(cases)} case(s) x {options['repeat']} "
            f"({ai_count} call OpenAI model {settings.OPENAI_EVALUATION_MODEL})."
        )

        with self._isolated_database():
            call_command("loaddata", str(bank), verbosity=0)
            # Integrity gates compare answers with the reviewed known-template catalog.
            call_command("load_known_answer_templates", "--confirm", stdout=io.StringIO())
            prepared, skipped = self._prepare(cases)
            runs = {case.id: [] for case, *_ in prepared}
            for round_number in range(1, options["repeat"] + 1):
                # Each round must reach the provider instead of reusing the previous round's results.
                EvaluationCache.objects.all().delete()
                with self._quiet(options["verbose"]), ThreadPoolExecutor(options["workers"]) as pool:
                    for case, observation in pool.map(self._evaluate, prepared):
                        runs[case.id].append(observation)
                        self.stdout.write(f"  [{round_number}] {case.id}: {observation.status}")
            connections.close_all()

        failures = self._report([item[0] for item in prepared], runs, skipped)
        if options["report"]:
            self._write_json(options["report"], [item[0] for item in prepared], runs, skipped)
        if failures:
            raise CommandError(f"{failures} case(s) failed without a documented known issue.")

    def _select(self, options):
        cases = [
            case for case in CASES
            if (not options["task"] or case.task in options["task"])
            and (not options["case"] or case.id in options["case"])
            and not (options["rule_only"] and uses_ai(case))
        ]
        if not cases:
            raise CommandError("No cases match the given filters.")
        return cases

    def _prepare(self, cases):
        prepared, skipped = [], {}
        for case in cases:
            question = Question.objects.select_related("subsection").filter(pk=case.question_id).first()
            if question is None or question.name != case.question_name:
                found = question.name if question else "nothing"
                raise CommandError(
                    f"{case.id}: question {case.question_id} should be {case.question_name!r}, "
                    f"found {found!r}. Update the case or use a matching export."
                )
            if case.task == "describe_image" and not self._image_available(question):
                skipped[case.id] = "question image missing; export without --skip-media to run"
                continue
            answer_data, transcript = build_submission(case, question)
            prepared.append((case, question, answer_data, transcript))
        return prepared, skipped

    @staticmethod
    def _image_available(question):
        return bool(question.image and question.image.name and question.image.storage.exists(question.image.name))

    def _evaluate(self, item):
        case, question, answer_data, transcript = item
        try:
            response = SingleResponse.objects.create(
                name=f"evaluation-case:{case.id}",
                question=question,
                # Pinned from the question paper, as the single-response API does.
                scoring_mode=question.mock_test_section.mock_test.scoring_mode,
                answer_data=answer_data,
                transcribed_audio_data=transcript,
            )
            # apply() runs the Celery task in-process, including its retries.
            evaluate_single_response.apply(args=[response.pk, question.pk])
            response.refresh_from_db()
            return case, observe(response)
        finally:
            connections.close_all()

    @contextlib.contextmanager
    def _isolated_database(self):
        settings_dict = connections["default"].settings_dict
        workdir = None
        if settings_dict["ENGINE"].endswith("sqlite3"):
            # A file database (not :memory:) so worker threads share it.
            workdir = tempfile.mkdtemp(prefix="evaluation-cases-")
            settings_dict["TEST"]["NAME"] = os.path.join(workdir, "cases.sqlite3")
            # IMMEDIATE avoids "database is locked" when threads upgrade read transactions.
            settings_dict.setdefault("OPTIONS", {}).update(timeout=60, transaction_mode="IMMEDIATE")
        old_config = setup_databases(verbosity=0, interactive=False, aliases={"default"}, serialized_aliases=set())
        try:
            if workdir:
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA journal_mode=WAL")
            yield
        finally:
            teardown_databases(old_config, verbosity=0)
            if workdir:
                shutil.rmtree(workdir, ignore_errors=True)

    @contextlib.contextmanager
    def _quiet(self, verbose):
        if verbose:
            yield
            return
        logging.disable(logging.WARNING)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                yield
        finally:
            logging.disable(logging.NOTSET)

    def _report(self, cases, runs, skipped):
        verdicts = Counter()
        unexpected = 0
        current_task = None
        self.stdout.write("")
        for case in cases:
            if case.task != current_task:
                current_task = case.task
                self.stdout.write(self.style.MIGRATE_HEADING(f"{case.task}  (question {case.question_id} {case.question_name})"))
            observations = runs[case.id]
            problems = [check_expectations(case.expect, observation) for observation in observations]
            passed = sum(not items for items in problems)
            verdict = "PASS" if passed == len(problems) else "FAIL" if passed == 0 else "FLAKY"
            if case.known_issue:
                verdict = "FIXED?" if verdict == "PASS" else "KNOWN"
            elif verdict != "PASS":
                unexpected += 1
            verdicts[verdict] += 1

            style = {"PASS": self.style.SUCCESS, "KNOWN": self.style.WARNING, "FIXED?": self.style.NOTICE}.get(
                verdict, self.style.ERROR
            )
            trainer = f" [{case.trainer_ref}]" if case.trainer_ref else ""
            runs_text = f" {passed}/{len(problems)}" if len(problems) > 1 else ""
            self.stdout.write(
                f"  {style(f'{verdict:6}')}{runs_text} {case.id:26} {case.label}{trainer}"
                f"\n           observed: {self._describe(observations[-1])}"
            )
            for reason in sorted({reason for items in problems for reason in items}):
                self.stdout.write(f"           - {reason}")
            if case.known_issue and verdict == "KNOWN":
                self.stdout.write(f"           known issue: {case.known_issue}")
        for case_id, reason in skipped.items():
            verdicts["SKIPPED"] += 1
            self.stdout.write(f"  SKIPPED {case_id}: {reason}")

        self.stdout.write("\n" + ", ".join(f"{name} {count}" for name, count in sorted(verdicts.items())))
        return unexpected

    @staticmethod
    def _describe(observation):
        if observation.status != "completed":
            return f"{observation.status} after {observation.attempts} attempt(s): {observation.error[:200]}"
        scores = ", ".join(
            f"{trait} {round(score, 2):g}/{maximum:g}" for trait, (score, maximum) in observation.scores.items()
        )
        text = f"traits {round(observation.total, 2):g}/{observation.maximum:g} ({scores})"
        if observation.awarded is not None:
            text += f"; awarded {round(observation.awarded, 2):g}" + (" (gated)" if observation.gated else "")
        if observation.overrides:
            text += f"; overrides: {', '.join(observation.overrides)}"
        return text

    def _write_json(self, path, cases, runs, skipped):
        payload = {
            "model": settings.OPENAI_EVALUATION_MODEL,
            "skipped": skipped,
            "cases": [
                {
                    "id": case.id, "task": case.task, "question_id": case.question_id,
                    "label": case.label, "trainer_ref": case.trainer_ref,
                    "known_issue": case.known_issue, "expect": case.expect,
                    "runs": [
                        {**vars(observation), "failures": check_expectations(case.expect, observation)}
                        for observation in runs[case.id]
                    ],
                }
                for case in cases
            ],
        }
        Path(path).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        self.stdout.write(f"Report written to {path}")
