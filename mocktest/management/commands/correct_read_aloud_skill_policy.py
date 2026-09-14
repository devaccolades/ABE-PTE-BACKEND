from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from examinor.scoring.contracts import VALID_SKILLS
from mocktest.models import (
    Question,
    SessionQuestion,
    SingleResponse,
    SubSection,
    UserMockTestSession,
    UserResponse,
)
from mocktest.services.question_config import canonical_trait_skill_map


class Command(BaseCommand):
    help = (
        "Correct Read Aloud to award Speaking only, update session snapshots, "
        "and rescore stored evaluations without calling an AI provider."
    )

    def add_arguments(self, parser):
        parser.add_argument("--reason")
        parser.add_argument("--expected-subsection-count", type=int)
        parser.add_argument("--expected-question-count", type=int)
        parser.add_argument("--expected-user-count", type=int)
        parser.add_argument("--expected-single-count", type=int)
        parser.add_argument("--expected-manifest-count", type=int)
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        plan = self._plan()
        self._print_plan(plan)
        if not options["confirm"]:
            self.stdout.write("Dry run only. No configuration or scores were changed.")
            return

        self._validate_confirmation(options, plan)
        with transaction.atomic():
            locked_plan = self._plan(lock=True)
            self._validate_confirmation(options, locked_plan)
            self._apply(locked_plan, options["reason"])

        self.stdout.write(self.style.SUCCESS(
            "Read Aloud now awards Speaking only. Corrected "
            f"{len(locked_plan['subsections'])} subsection(s), "
            f"{len(locked_plan['questions'])} question maximum(s), "
            f"{len(locked_plan['manifests'])} session snapshot(s), and rescored "
            f"{len(locked_plan['user_responses'])} UserResponse(s), "
            f"{len(locked_plan['single_responses'])} SingleResponse(s), and "
            f"{len(locked_plan['session_ids'])} session(s). No AI provider was called."
        ))

    @staticmethod
    def _plan(*, lock=False):
        subsections = SubSection.objects.filter(name="read_aloud").order_by("pk")
        if lock:
            subsections = subsections.select_for_update()

        subsection_rows = []
        for subsection in list(subsections):
            corrected, changed = canonical_trait_skill_map(subsection)
            if changed:
                subsection_rows.append((subsection, corrected))

        questions = Question.objects.filter(
            subsection__name="read_aloud",
        ).order_by("pk")
        if lock:
            questions = questions.select_for_update()
        all_questions = list(questions)
        question_rows = [
            question
            for question in all_questions
            if float(question.reading_score_max or 0) > 0
        ]
        changed_subsection_ids = {
            subsection.pk for subsection, _ in subsection_rows
        }
        affected_question_ids = {
            question.pk
            for question in all_questions
            if question.pk in {item.pk for item in question_rows}
            or question.subsection_id in changed_subsection_ids
        }

        manifests = SessionQuestion.objects.filter(
            question_id_snapshot__in=[question.pk for question in all_questions],
        ).order_by("pk")
        if lock:
            manifests = manifests.select_for_update()
        manifest_rows = [row for row in manifests if Command._manifest_needs_update(row)]
        affected_question_ids.update(
            row.question_id_snapshot for row in manifest_rows
        )

        user_responses = UserResponse.objects.filter(
            question_id__in=affected_question_ids,
            evaluated=True,
            evaluation_result__isnull=False,
        ).order_by("pk")
        single_responses = SingleResponse.objects.filter(
            question_id__in=affected_question_ids,
            evaluated=True,
            evaluation_result__isnull=False,
        ).order_by("pk")
        if lock:
            user_responses = user_responses.select_for_update()
            single_responses = single_responses.select_for_update()

        if lock:
            # PostgreSQL cannot lock the nullable side of the subsection join.
            # Question and subsection configuration rows are locked separately above.
            user_rows = list(user_responses)
            single_rows = list(single_responses)
        else:
            user_rows = list(
                user_responses.select_related("question__subsection")
            )
            single_rows = list(
                single_responses.select_related("question__subsection")
            )
        session_ids = {
            response.user_session_id for response in user_rows
        } | {row.session_id for row in manifest_rows}
        return {
            "subsections": subsection_rows,
            "questions": question_rows,
            "user_responses": user_rows,
            "single_responses": single_rows,
            "manifests": manifest_rows,
            "session_ids": session_ids,
        }

    @staticmethod
    def _manifest_needs_update(row):
        maxima = row.skill_maxima_snapshot or {}
        if float(maxima.get("reading") or 0) > 0:
            return True
        trait_map = row.trait_skill_map_snapshot or {}
        for trait in ("content", "oral_fluency", "pronunciation"):
            skills = trait_map.get(trait, [])
            if isinstance(skills, str):
                skills = [skills]
            if "reading" in skills:
                return True
        return False

    def _apply(self, plan, reason):
        corrected_at = timezone.now().isoformat()
        for subsection, trait_map in plan["subsections"]:
            SubSection.objects.filter(pk=subsection.pk).update(
                trait_skill_map=trait_map
            )
        Question.objects.filter(
            pk__in=[question.pk for question in plan["questions"]]
        ).update(reading_score_max=None)

        for row in plan["manifests"]:
            trait_map = dict(row.trait_skill_map_snapshot or {})
            for trait in ("content", "oral_fluency", "pronunciation"):
                if trait in trait_map:
                    trait_map[trait] = ["speaking"]
            maxima = dict(row.skill_maxima_snapshot or {})
            maxima["reading"] = 0.0
            row.trait_skill_map_snapshot = trait_map
            row.skill_maxima_snapshot = maxima
            row.save(update_fields=[
                "trait_skill_map_snapshot",
                "skill_maxima_snapshot",
            ])

        for model_name, responses in (
            ("UserResponse", plan["user_responses"]),
            ("SingleResponse", plan["single_responses"]),
        ):
            for response in responses:
                before = self._awarded(response)
                response.apply_skill_scores()
                after = self._awarded(response)
                result = dict(response.evaluation_result or {})
                history = list(result.get("score_corrections") or [])
                history.append({
                    "corrected_at": corrected_at,
                    "source": "correct_read_aloud_skill_policy",
                    "model": model_name,
                    "question_id": response.question_id,
                    "policy_before": "reading_and_speaking",
                    "policy_after": "speaking_only",
                    "awarded_before": before,
                    "awarded_after": after,
                    "reason": reason,
                })
                result["score_corrections"] = history
                response.evaluation_result = result
                response.save(update_fields=["evaluation_result"])

        sessions = UserMockTestSession.objects.select_for_update().filter(
            pk__in=plan["session_ids"]
        )
        for session in sessions:
            session.aggregate_scores()

    @staticmethod
    def _awarded(response):
        return {
            skill: float(getattr(response, f"{skill}_score_awarded") or 0)
            for skill in VALID_SKILLS
        }

    def _print_plan(self, plan):
        self.stdout.write("Read Aloud skill policy correction")
        self.stdout.write("==================================")
        self.stdout.write("Current policy: Speaking only")
        self.stdout.write(f"Subsections requiring mapping correction: {len(plan['subsections'])}")
        self.stdout.write(f"Questions with Reading maxima to clear: {len(plan['questions'])}")
        self.stdout.write(f"Session snapshots to correct: {len(plan['manifests'])}")
        self.stdout.write(f"Evaluated UserResponses to rescore: {len(plan['user_responses'])}")
        self.stdout.write(f"Evaluated SingleResponses to rescore: {len(plan['single_responses'])}")
        self.stdout.write(f"Sessions to recalculate: {len(plan['session_ids'])}")

    @staticmethod
    def _validate_confirmation(options, plan):
        if not options["confirm"]:
            return
        if not options["reason"]:
            raise CommandError("--reason is required with --confirm.")
        expected = {
            "subsections": options["expected_subsection_count"],
            "questions": options["expected_question_count"],
            "user_responses": options["expected_user_count"],
            "single_responses": options["expected_single_count"],
            "manifests": options["expected_manifest_count"],
        }
        for key, count in expected.items():
            if count is None or count < 0:
                raise CommandError(
                    "All --expected-*-count guards are required with --confirm."
                )
            actual = len(plan[key])
            if actual != count:
                raise CommandError(
                    f"Expected {count} {key.replace('_', ' ')}, found {actual}. "
                    "Nothing was changed."
                )
