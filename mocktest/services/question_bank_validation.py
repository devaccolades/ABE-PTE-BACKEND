from examinor.services.rule_evaluator import run_rule_evaluation, uses_rule_evaluation
from mocktest.services.question_config import (
    CANONICAL_TRAIT_SKILL_CONTRACTS,
    VALID_SKILLS,
)
from mocktest.services.question_maximum_policy import maximum_policy_rows


MEDIA_REQUIRED_SECTIONS = {"Listening"}
IMAGE_REQUIRED_SUBSECTIONS = {"describe_image"}


class EmptyAnswer:
    answer_data = {}


class QuestionBankAuditor:
    def __init__(self, *, check_storage=True, include_response_context=True):
        self.check_storage = check_storage
        self.include_response_context = include_response_context
        self._context_cache = {}
        self._subsection_issues = set()
        self._global_rubric_cache = {}

    def audit(self, questions):
        issues = []
        for question in questions:
            issues.extend(self.question_issues(question))
        return issues

    def question_issues(self, question):
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
            self._check_file(question, question.audio, "audio", add)

        if subsection.name in IMAGE_REQUIRED_SUBSECTIONS:
            self._check_file(question, question.image, "image", add)

        if subsection.name == "summarize_spoken_text":
            if not question.correct_answer:
                add(
                    "error",
                    "missing_ai_reference",
                    "Summarize Spoken Text has no reference material.",
                    "Add a source transcript, model answer, or key points to Question.correct_answer.",
                )
        elif uses_rule_evaluation(subsection):
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

        rubric = dict(subsection.rubric or {})
        if not rubric:
            add(
                "error",
                "missing_rubric",
                "Subsection rubric is empty, so no score can be calculated.",
                "Configure the scoring rubric on the subsection.",
            )

        for trait, enabled in (
            ("pronunciation", subsection.use_pronunciation),
            ("oral_fluency", subsection.use_fluency),
        ):
            if not enabled or trait in rubric:
                continue
            global_rubric = self._global_rubric(trait)
            if not global_rubric:
                add(
                    "error",
                    "missing_global_rubric",
                    f"Subsection enables {trait}, but its global rubric is missing or empty.",
                    f"Create a non-empty GlobalRubric with key '{trait}'.",
                )
                continue
            rubric[trait] = global_rubric

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

        for policy_row in maximum_policy_rows(question):
            if policy_row["severity"] != "error":
                continue
            skill = policy_row["skill"] or "unknown"
            if policy_row["status"] == "missing" and skill in mapped_skills:
                continue
            configured = policy_row["configured_maximum"]
            expected = policy_row["expected_maximum"]
            add(
                "error",
                f"question_skill_maximum_{policy_row['status']}",
                (
                    f"Question {skill} maximum is {configured!s} but the "
                    f"authoritative task policy expects {expected!s}. "
                    f"Basis: {policy_row['basis']}"
                ),
                policy_row["manual_action"],
            )

        return issues

    def _global_rubric(self, key):
        if key not in self._global_rubric_cache:
            from mocktest.models import GlobalRubric

            value = GlobalRubric.objects.filter(key=key).values_list(
                "rubric", flat=True
            ).first()
            self._global_rubric_cache[key] = value or None
        return self._global_rubric_cache[key]

    def _add_subsection_issue(self, issues, question, code, problem, fix):
        key = (question.subsection_id, code, problem)
        if key in self._subsection_issues:
            return
        self._subsection_issues.add(key)
        issues.append(self._issue_row(question, "error", code, problem, fix))

    def _check_file(self, question, field, kind, add):
        if not field:
            add(
                "error",
                f"missing_{kind}",
                f"Question has no configured {kind} file.",
                f"Upload the required question {kind} file.",
            )
            return
        if not self.check_storage:
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
        session_labels = []
        response_test_titles = []
        if self.include_response_context:
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
            session_labels = [
                f"{name} [{session_id}]" for name, session_id, _ in response_sessions
            ]
            response_test_titles = sorted(
                {title for _, _, title in response_sessions if title}
            )
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

    @staticmethod
    def _answer_key_fix(subsection_name):
        if subsection_name == "l_fill_in_blanks":
            return "Add each missing word to ordered SubQuestion.correct_answer rows."
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


def question_bank_queryset(*, section=None, subsection=None, mock_test=None):
    from mocktest.models import Question

    questions = (
        Question.objects.select_related(
            "subsection__section",
            "mock_test_section__mock_test",
            "mock_test_section__section",
        )
        .prefetch_related("sub_questions", "options")
        .order_by("pk")
    )
    if section:
        questions = questions.filter(subsection__section__name__iexact=section)
    if subsection:
        questions = questions.filter(subsection__name__iexact=subsection)
    if mock_test is not None:
        questions = questions.filter(mock_test_section__mock_test=mock_test)
    return questions


def mock_test_publication_issues(mock_test, *, check_storage=True):
    issues = []
    sections = list(mock_test.sections.select_related("section").order_by("order", "pk"))

    def test_issue(code, problem, fix):
        issues.append(
            {
                "severity": "error",
                "code": code,
                "mock_test": mock_test.title,
                "mock_test_id": str(mock_test.pk),
                "question_id": "",
                "question_name": "-",
                "section": "-",
                "subsection": "-",
                "affected_session_count": 0,
                "affected_sessions": "",
                "problem": problem,
                "manual_fix": fix,
            }
        )

    if not sections:
        test_issue(
            "missing_mock_test_sections",
            "Mock test has no sections.",
            "Add the required mock-test sections before activation.",
        )
        return issues

    seen_orders = set()
    for mock_test_section in sections:
        if mock_test_section.section is None:
            test_issue(
                "missing_mock_test_section",
                f"Mock-test section {mock_test_section.pk} has no section.",
                "Assign the mock-test section to a valid section.",
            )
        if mock_test_section.order in seen_orders:
            test_issue(
                "duplicate_section_order",
                f"More than one mock-test section uses order {mock_test_section.order}.",
                "Give every mock-test section a unique order.",
            )
        seen_orders.add(mock_test_section.order)
        if not mock_test_section.questions.exists():
            section_name = mock_test_section.section.name if mock_test_section.section else "Unassigned"
            test_issue(
                "empty_mock_test_section",
                f"Mock-test section '{section_name}' has no questions.",
                "Add at least one question or remove the empty section.",
            )

    auditor = QuestionBankAuditor(
        check_storage=check_storage,
        include_response_context=False,
    )
    issues.extend(
        auditor.audit(question_bank_queryset(mock_test=mock_test))
    )
    return issues


def publication_errors(mock_test, *, check_storage=True):
    return [
        issue
        for issue in mock_test_publication_issues(
            mock_test,
            check_storage=check_storage,
        )
        if issue["severity"] == "error"
    ]
