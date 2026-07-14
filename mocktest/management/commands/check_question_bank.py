import csv
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from examinor.services.rule_evaluator import (
    RULE_QUESTION_CONFIG,
    run_rule_evaluation,
)
from mocktest.models import Question
from mocktest.services.question_config import (
    CANONICAL_TRAIT_SKILL_CONTRACTS,
    VALID_SKILLS,
)


MEDIA_REQUIRED_SECTIONS = {"Listening"}
IMAGE_REQUIRED_SUBSECTIONS = {"describe_image"}


class EmptyAnswer:
    answer_data = {}


class Command(BaseCommand):
    help = "Audit the complete question bank and write a handoff-ready CSV report."

    def add_arguments(self, parser):
        parser.add_argument("--section", help="Only inspect one section name.")
        parser.add_argument(
            "--output",
            default="question_bank_audit.csv",
            help="CSV report path (default: question_bank_audit.csv).",
        )
        parser.add_argument(
            "--skip-media-check",
            action="store_true",
            help="Check media field configuration without checking storage.",
        )
        parser.add_argument(
            "--warnings-as-errors",
            action="store_true",
            help="Return a failing exit code when warnings are present.",
        )

    def handle(self, *args, **options):
        self._context_cache = {}
        self._subsection_issues = set()
        questions = (
            Question.objects.select_related(
                "subsection__section",
                "mock_test_section__mock_test",
                "mock_test_section__section",
            )
            .prefetch_related("sub_questions", "options")
            .order_by("pk")
        )
        if options["section"]:
            questions = questions.filter(
                subsection__section__name__iexact=options["section"]
            )

        issues = []
        question_count = 0
        for question in questions:
            question_count += 1
            issues.extend(
                self._question_issues(
                    question,
                    check_storage=not options["skip_media_check"],
                )
            )

        self._write_report(options["output"], issues)
        counts = Counter(issue["severity"] for issue in issues)
        affected = len({issue["question_id"] for issue in issues})

        self.stdout.write("Question bank audit")
        self.stdout.write("===================")
        self.stdout.write(f"Questions checked: {question_count}")
        self.stdout.write(f"Affected questions: {affected}")
        self.stdout.write(f"Errors: {counts['error']}")
        self.stdout.write(f"Warnings: {counts['warning']}")
        self.stdout.write(f"Report: {Path(options['output']).resolve()}")

        for issue in issues:
            self.stdout.write(
                " | ".join(
                    [
                        issue["severity"].upper(),
                        f"mock_test={issue['mock_test']}",
                        f"question={issue['question_id']} ({issue['question_name']})",
                        f"section={issue['section']}",
                        f"subsection={issue['subsection']}",
                        f"code={issue['code']}",
                        issue["problem"],
                    ]
                )
            )

        should_fail = counts["error"] or (
            options["warnings_as_errors"] and counts["warning"]
        )
        if should_fail:
            raise CommandError("Question bank audit found configuration problems.")

        self.stdout.write(self.style.SUCCESS("Question bank configuration looks healthy."))

    def _question_issues(self, question, check_storage):
        issues = []

        def add(severity, code, problem, fix):
            issues.append(self._issue_row(question, severity, code, problem, fix))

        subsection = question.subsection
        if subsection is None:
            add(
                "error",
                "missing_subsection",
                "Question has no subsection.",
                "Assign the question to the correct subsection.",
            )
            return issues

        section = subsection.section
        if section is None:
            add(
                "error",
                "missing_section",
                "The question subsection has no section.",
                "Assign the subsection to Speaking, Writing, Reading, or Listening.",
            )

        if question.mock_test_section is None:
            add(
                "warning",
                "unassigned_mock_test",
                "Question is not assigned to a mock-test section.",
                "Assign a mock-test section or confirm this is an intentionally unused bank question.",
            )
        elif section and question.mock_test_section.section_id != section.id:
            add(
                "error",
                "section_mismatch",
                "Question subsection and mock-test section belong to different sections.",
                "Make both associations point to the same exam section.",
            )

        if not question.name and not question.text:
            add(
                "error",
                "missing_prompt",
                "Question has neither a name nor prompt text.",
                "Add a stable question name and the candidate-facing prompt where applicable.",
            )

        section_name = section.name if section and section.name else ""
        if section_name in MEDIA_REQUIRED_SECTIONS:
            self._check_file(
                question,
                question.audio,
                "audio",
                check_storage,
                add,
            )

        if subsection.name in IMAGE_REQUIRED_SUBSECTIONS:
            self._check_file(
                question,
                question.image,
                "image",
                check_storage,
                add,
            )

        if subsection.name == "summarize_spoken_text":
            if not question.correct_answer:
                add(
                    "error",
                    "missing_ai_reference",
                    "Summarize Spoken Text has no reference material.",
                    "Add a source transcript, model answer, or key points to Question.correct_answer.",
                )
        elif subsection.name in RULE_QUESTION_CONFIG or subsection.evaluation_type == "rule":
            result = run_rule_evaluation(
                user_answer=EmptyAnswer(),
                question=question,
                subsection=subsection,
            )
            if not result.get("ok", False):
                add(
                    "error",
                    "invalid_answer_key",
                    result.get("error", "Invalid deterministic answer configuration."),
                    self._answer_key_fix(subsection.name),
                )

        rubric = subsection.rubric or {}
        if not rubric:
            add(
                "error",
                "missing_rubric",
                "Subsection rubric is empty, so no score can be calculated.",
                "Configure the scoring rubric on the subsection.",
            )

        trait_map = subsection.trait_skill_map or {}
        mapped_skills = set()
        if not trait_map:
            add(
                "error",
                "missing_trait_skill_map",
                "Subsection trait-to-skill map is empty, so awarded traits become zero skill points.",
                "Map every rubric trait to its PTE skill or skills.",
            )
        else:
            for trait in rubric:
                skills = trait_map.get(trait)
                if not skills:
                    add(
                        "error",
                        "unmapped_rubric_trait",
                        f"Rubric trait '{trait}' is not mapped to a skill.",
                        f"Add '{trait}' to SubSection.trait_skill_map.",
                    )
                    continue
                if isinstance(skills, str):
                    skills = [skills]
                invalid = sorted(set(skills) - VALID_SKILLS)
                if invalid:
                    add(
                        "error",
                        "invalid_skill_name",
                        f"Trait '{trait}' maps to unsupported skill(s): {', '.join(invalid)}.",
                        "Use only speaking, writing, reading, and listening.",
                    )
                mapped_skills.update(set(skills) & VALID_SKILLS)

                required = CANONICAL_TRAIT_SKILL_CONTRACTS.get(
                    (subsection.name, trait)
                )
                if required:
                    actual = set(skills) & VALID_SKILLS
                    missing = sorted(required - actual)
                    unexpected = sorted(actual - required)
                    if missing or unexpected:
                        parts = []
                        if missing:
                            parts.append(f"missing {', '.join(missing)}")
                        if unexpected:
                            parts.append(f"must not award {', '.join(unexpected)}")
                        self._add_subsection_issue(
                            issues,
                            question,
                            "invalid_trait_skill_contract",
                            (
                                f"Shared {subsection.name} trait '{trait}' mapping is invalid: "
                                f"{'; '.join(parts)}."
                            ),
                            (
                                f"Set SubSection.trait_skill_map['{trait}'] to "
                                f"{sorted(required)}. This is a shared subsection fix."
                            ),
                        )
                    mapped_skills.difference_update(actual - required)
                    mapped_skills.update(required)

            for skill in sorted(mapped_skills):
                maximum = getattr(question, f"{skill}_score_max") or 0
                if maximum <= 0:
                    add(
                        "error",
                        "missing_question_skill_max",
                        f"Question awards {skill}, but its {skill} maximum is zero.",
                        f"Set Question.{skill}_score_max to the intended maximum.",
                    )

        return issues

    def _add_subsection_issue(self, issues, question, code, problem, fix):
        key = (question.subsection_id, code, problem)
        if key in self._subsection_issues:
            return
        self._subsection_issues.add(key)
        issues.append(self._issue_row(question, "error", code, problem, fix))

    def _check_file(self, question, field, kind, check_storage, add):
        if not field:
            add(
                "error",
                f"missing_{kind}",
                f"Question has no configured {kind} file.",
                f"Upload the required question {kind} file.",
            )
            return
        if not check_storage:
            return
        try:
            exists = field.storage.exists(field.name)
        except Exception as exc:
            add(
                "error",
                f"{kind}_storage_error",
                f"Could not verify {kind} file '{field.name}': {exc}",
                "Check media storage credentials and file availability.",
            )
            return
        if not exists:
            add(
                "error",
                f"missing_{kind}_file",
                f"Configured {kind} file does not exist in storage: {field.name}",
                "Restore the media file from backup or upload a replacement.",
            )

    def _issue_row(self, question, severity, code, problem, fix):
        context = self._question_context(question)
        return {
            "severity": severity,
            "code": code,
            **context,
            "problem": problem,
            "manual_fix": fix,
        }

    def _question_context(self, question):
        if question.pk in self._context_cache:
            return self._context_cache[question.pk]

        subsection = question.subsection
        section = subsection.section if subsection else None
        mock_test = (
            question.mock_test_section.mock_test
            if question.mock_test_section and question.mock_test_section.mock_test
            else None
        )
        response_sessions = list(
            question.userresponse_set.select_related("user_session", "mock_test")
            .order_by("user_session__name", "user_session__session_id")
            .values_list(
                "user_session__name",
                "user_session__session_id",
                "mock_test__title",
            )
            .distinct()
        )
        session_labels = [f"{name} [{session_id}]" for name, session_id, _ in response_sessions]
        response_test_titles = sorted({title for _, _, title in response_sessions if title})
        mock_test_title = mock_test.title if mock_test else ", ".join(response_test_titles)

        context = {
            "mock_test": mock_test_title or "Unassigned",
            "mock_test_id": str(mock_test.pk) if mock_test else "",
            "question_id": question.pk,
            "question_name": question.name or "-",
            "section": section.name if section and section.name else "Unassigned",
            "subsection": subsection.name if subsection else "Unassigned",
            "affected_session_count": len(session_labels),
            "affected_sessions": "; ".join(session_labels),
        }
        self._context_cache[question.pk] = context
        return context

    def _answer_key_fix(self, subsection_name):
        if subsection_name == "l_fill_in_blanks":
            return "Add each missing word to ordered SubQuestion.correct_answer rows."
        if subsection_name == "highlight_incorrect_words":
            return "Set Question.correct_answer to the accurate transcript or pipe-separated incorrect words."
        if subsection_name == "write_from_dictation":
            return "Set Question.correct_answer to the exact spoken sentence."
        if subsection_name in {
            "mc_single",
            "l_mc_single",
            "highlight_correct_summary",
            "select_missing_word",
            "fib_dropdown",
            "mc_multiple",
            "l_mc_multiple",
        }:
            return "Review the options and mark the required option or options as correct."
        return "Correct the answer metadata described in the problem column."

    def _write_report(self, output, issues):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = [
            "severity",
            "code",
            "mock_test",
            "mock_test_id",
            "question_id",
            "question_name",
            "section",
            "subsection",
            "affected_session_count",
            "affected_sessions",
            "problem",
            "manual_fix",
        ]
        with path.open("w", newline="", encoding="utf-8") as report:
            writer = csv.DictWriter(report, fieldnames=columns)
            writer.writeheader()
            writer.writerows(issues)
