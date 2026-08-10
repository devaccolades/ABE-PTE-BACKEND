import math

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from examinor.scoring.contracts import VALID_SKILLS
from examinor.scoring.response_scores import (
    compile_response_score_evidence,
    promoted_skill_values,
    response_scoring_mode,
)
from mocktest.models import Question, SingleResponse, UserMockTestSession, UserResponse


class Command(BaseCommand):
    help = (
        "Correct one confirmed question skill maximum and transactionally rescore "
        "stored evaluated responses without calling an AI provider. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument("--question-id", type=int, required=True)
        parser.add_argument("--skill", choices=sorted(VALID_SKILLS), required=True)
        parser.add_argument("--expected-current", type=float, required=True)
        parser.add_argument("--new-maximum", type=float, required=True)
        parser.add_argument("--reason")
        parser.add_argument("--expected-user-count", type=int)
        parser.add_argument("--expected-single-count", type=int)
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        self._validate_options(options)
        question = Question.objects.select_related(
            "subsection",
            "mock_test_section__mock_test",
        ).get(pk=options["question_id"])
        field = f"{options['skill']}_score_max"
        self._check_current(question, field, options["expected_current"])
        self._check_skill_mapping(question, options["skill"])

        user_responses = list(
            UserResponse.objects.filter(
                question=question,
                evaluated=True,
                evaluation_result__isnull=False,
            ).select_related("user_session")
        )
        single_responses = list(
            SingleResponse.objects.filter(
                question=question,
                evaluated=True,
                evaluation_result__isnull=False,
            )
        )
        proposals = self._proposals(
            question,
            field,
            options["skill"],
            options["new_maximum"],
            user_responses,
            single_responses,
        )

        self._print_plan(question, field, options, proposals)
        if not options["confirm"]:
            self.stdout.write("Dry run only. No question or score data was changed.")
            return

        self._check_expected_counts(options, user_responses, single_responses)
        self._apply(options, field)

    def _apply(self, options, field):
        question_id = options["question_id"]
        skill = options["skill"]
        old_maximum = options["expected_current"]
        new_maximum = options["new_maximum"]
        now = timezone.now().isoformat()

        with transaction.atomic():
            question = Question.objects.select_for_update().get(pk=question_id)
            self._check_current(question, field, old_maximum)
            self._check_skill_mapping(question, skill)

            user_responses = list(
                UserResponse.objects.select_for_update().filter(
                    question=question,
                    evaluated=True,
                    evaluation_result__isnull=False,
                ).select_related("user_session")
            )
            single_responses = list(
                SingleResponse.objects.select_for_update().filter(
                    question=question,
                    evaluated=True,
                    evaluation_result__isnull=False,
                )
            )
            self._check_expected_counts(options, user_responses, single_responses)

            setattr(question, field, new_maximum)
            question.save(update_fields=[field])

            session_ids = set()
            for model_name, responses in (
                ("UserResponse", user_responses),
                ("SingleResponse", single_responses),
            ):
                for response in responses:
                    before = self._awarded_scores(response)
                    response.question = question
                    response.apply_skill_scores()
                    after = self._awarded_scores(response)
                    self._record_correction(
                        response,
                        model_name=model_name,
                        skill=skill,
                        old_maximum=old_maximum,
                        new_maximum=new_maximum,
                        before=before,
                        after=after,
                        reason=options["reason"],
                        corrected_at=now,
                    )
                    if model_name == "UserResponse":
                        session_ids.add(response.user_session_id)

            sessions = list(
                UserMockTestSession.objects.select_for_update().filter(
                    pk__in=session_ids
                )
            )
            for session in sessions:
                session.aggregate_scores()

        self.stdout.write(
            self.style.SUCCESS(
                f"Corrected question {question_id} {skill} maximum "
                f"from {old_maximum:g} to {new_maximum:g}; rescored "
                f"{len(user_responses)} UserResponse(s), "
                f"{len(single_responses)} SingleResponse(s), and "
                f"{len(sessions)} session(s). No AI provider was called."
            )
        )

    @staticmethod
    def _proposals(
        question,
        field,
        skill,
        new_maximum,
        user_responses,
        single_responses,
    ):
        original = getattr(question, field)
        setattr(question, field, new_maximum)
        rows = []
        try:
            for model_name, responses in (
                ("UserResponse", user_responses),
                ("SingleResponse", single_responses),
            ):
                for response in responses:
                    evidence = compile_response_score_evidence(
                        question,
                        response.evaluation_result,
                        mode=response_scoring_mode(response),
                    )
                    rows.append({
                        "model": model_name,
                        "response_id": response.pk,
                        "session_id": (
                            response.user_session_id
                            if model_name == "UserResponse"
                            else ""
                        ),
                        "current_award": getattr(
                            response,
                            f"{skill}_score_awarded",
                        ),
                        "proposed_award": promoted_skill_values(evidence)[skill],
                    })
        finally:
            setattr(question, field, original)
        return rows

    def _print_plan(self, question, field, options, proposals):
        mock_test = (
            question.mock_test_section.mock_test.title
            if question.mock_test_section_id
            else "Unassigned"
        )
        self.stdout.write("Question skill maximum correction")
        self.stdout.write("=================================")
        self.stdout.write(f"Question: {question.pk} ({question.name or '-'})")
        self.stdout.write(f"Mock test: {mock_test}")
        self.stdout.write(f"Field: {field}")
        self.stdout.write(f"Current maximum: {options['expected_current']:g}")
        self.stdout.write(f"Proposed maximum: {options['new_maximum']:g}")
        self.stdout.write(
            f"Evaluated UserResponses: "
            f"{sum(row['model'] == 'UserResponse' for row in proposals)}"
        )
        self.stdout.write(
            f"Evaluated SingleResponses: "
            f"{sum(row['model'] == 'SingleResponse' for row in proposals)}"
        )
        for row in proposals:
            self.stdout.write(
                f"model={row['model']} | response={row['response_id']} "
                f"| session={row['session_id']} "
                f"| current_{options['skill']}={row['current_award']:g} "
                f"| proposed_{options['skill']}={row['proposed_award']:g}"
            )

    @staticmethod
    def _record_correction(
        response,
        *,
        model_name,
        skill,
        old_maximum,
        new_maximum,
        before,
        after,
        reason,
        corrected_at,
    ):
        result = dict(response.evaluation_result or {})
        history = list(result.get("score_corrections") or [])
        history.append({
            "corrected_at": corrected_at,
            "source": "correct_question_skill_maximum",
            "model": model_name,
            "question_id": response.question_id,
            "skill": skill,
            "maximum_before": old_maximum,
            "maximum_after": new_maximum,
            "awarded_before": before,
            "awarded_after": after,
            "reason": reason,
        })
        result["score_corrections"] = history
        response.evaluation_result = result
        response.save(update_fields=["evaluation_result"])

    @staticmethod
    def _awarded_scores(response):
        return {
            skill: float(getattr(response, f"{skill}_score_awarded") or 0)
            for skill in VALID_SKILLS
        }

    @staticmethod
    def _validate_options(options):
        for key in ("expected_current", "new_maximum"):
            value = options[key]
            if not math.isfinite(value) or value <= 0:
                raise CommandError(f"--{key.replace('_', '-')} must be positive and finite.")
        if math.isclose(
            options["expected_current"],
            options["new_maximum"],
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise CommandError("The current and proposed maxima are equal.")
        if options["confirm"]:
            if not options["reason"]:
                raise CommandError("--reason is required with --confirm.")
            for key in ("expected_user_count", "expected_single_count"):
                if options[key] is None or options[key] < 0:
                    raise CommandError(
                        f"--{key.replace('_', '-')} is required with --confirm."
                    )

    @staticmethod
    def _check_current(question, field, expected):
        current = getattr(question, field)
        if current is None or not math.isclose(
            float(current),
            expected,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise CommandError(
                f"Current {field} is {current!r}; expected {expected:g}. "
                "Nothing was changed."
            )

    @staticmethod
    def _check_skill_mapping(question, skill):
        mapped = set()
        for skills in (question.subsection.trait_skill_map or {}).values():
            if isinstance(skills, str):
                skills = [skills]
            mapped.update(skills)
        if skill not in mapped:
            raise CommandError(
                f"Question {question.pk} has no rubric trait mapped to {skill}. "
                "Nothing was changed."
            )

    @staticmethod
    def _check_expected_counts(options, user_responses, single_responses):
        expected_user = options["expected_user_count"]
        expected_single = options["expected_single_count"]
        if len(user_responses) != expected_user:
            raise CommandError(
                f"Evaluated UserResponse count changed: expected {expected_user}, "
                f"found {len(user_responses)}. Nothing was changed."
            )
        if len(single_responses) != expected_single:
            raise CommandError(
                f"Evaluated SingleResponse count changed: expected {expected_single}, "
                f"found {len(single_responses)}. Nothing was changed."
            )
