import uuid
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone
import logging

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


SCORING_MODE_CHOICES = (
    ("legacy", "Legacy"),
    ("shadow", "Shadow V2"),
    ("v2", "V2"),
)


def default_session_scoring_mode():
    from examinor.scoring.response_scores import configured_scoring_mode

    return configured_scoring_mode()


class MockTest(models.Model):
    test_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    total_score = models.PositiveIntegerField(
        default=0, help_text="Maximum total score for the test"
    )
    total_duration = models.PositiveIntegerField(
        help_text="Duration in seconds", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=False,
        help_text="Draft mock tests must pass publication validation before activation.",
    )
    scoring_mode = models.CharField(
        max_length=10,
        choices=SCORING_MODE_CHOICES,
        default="shadow",
        help_text="Scoring mode inherited by newly started sessions.",
    )

    def save(self, *args, **kwargs):
        being_activated = self._is_being_activated()
        enabling_v2 = self._is_enabling_v2()
        if enabling_v2 and not self.is_active:
            raise ValidationError(
                {"scoring_mode": "V2 can only be enabled for an active mock test."}
            )
        if (being_activated or enabling_v2) and not getattr(
            self, "_publication_validation_passed", False
        ):
            if not self.pk:
                raise ValidationError(
                    {
                        "is_active": (
                            "Save the mock test as a draft before activating it "
                            "or enabling V2."
                        )
                    }
                )
            from mocktest.services.question_bank_validation import publication_errors

            errors = publication_errors(self)
            if errors:
                details = "; ".join(
                    f"{issue['code']}: {issue['problem']}" for issue in errors[:10]
                )
                if len(errors) > 10:
                    details += f"; and {len(errors) - 10} more error(s)"
                raise ValidationError(
                    {
                        "scoring_mode" if enabling_v2 else "is_active": (
                            "Mock test cannot be activated or moved to V2. "
                            f"{details}"
                        )
                    }
                )
        try:
            super().save(*args, **kwargs)
        finally:
            if hasattr(self, "_publication_validation_passed"):
                del self._publication_validation_passed

    def _is_being_activated(self):
        if not self.is_active:
            return False
        if not self.pk:
            return True
        previous = type(self).objects.filter(pk=self.pk).values_list(
            "is_active", flat=True
        ).first()
        return previous is False

    def _is_enabling_v2(self):
        if self.scoring_mode != "v2":
            return False
        if not self.pk:
            return True
        previous = type(self).objects.filter(pk=self.pk).values_list(
            "scoring_mode", flat=True
        ).first()
        return previous != "v2"

    def __str__(self):
        return self.title


class Section(models.Model):
    """
    Main sections linked to both a Skill and an Exam Part.
    Example: Speaking section inside 'Part 1: Speaking & Writing'
    """

    name = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.name}"


class MockTestSection(models.Model):
    mock_test = models.ForeignKey(
        MockTest,
        on_delete=models.CASCADE,
        related_name="sections",
        null=True,
        blank=True,
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="mock_test_sections",
        null=True,
        blank=True,
    )
    order = models.PositiveIntegerField(default=1)
    total_duration = models.PositiveIntegerField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.pk:
            _protect_active_session_question_config(
                Question.objects.filter(mock_test_section_id=self.pk).values_list(
                    "pk",
                    flat=True,
                ),
                "Mock-test sections",
            )
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.mock_test.title} - {self.section.name}"


class GlobalRubric(models.Model):
    key = models.CharField(max_length=50, unique=True)
    rubric = models.JSONField()

    def __str__(self):
        return self.key


class SubSection(models.Model):
    """
    Detailed subsections like 'Read Aloud', 'Describe Image', etc.
    """

    SUBSECTION_CHOICES = [
        # Speaking
        ("read_aloud", "Read Aloud"),
        ("repeat_sentence", "Repeat Sentence"),
        ("describe_image", "Describe Image"),
        ("retell_lecture", "Retell Lecture"),
        ("answer_short_question", "Answer Short Question"),
        ("summarise_group_discussion", "Summarise Group Discussion"),
        ("respond_to_a_situation", "Respond to a Situation"),
        # Writing
        ("summarize_written_text", "Summarize Written Text"),
        ("write_essay", "Write Essay"),
        # Reading
        ("fib_dropdown", "Fill in the Blanks – Dropdown"),
        ("mc_multiple", "MCQ – Multiple Answers (Reading)"),
        ("reorder_paragraphs", "Reorder Paragraphs"),
        ("fib_drag_drop", "Fill in the Blanks – Drag & Drop"),
        ("mc_single", "MCQ – Single Answer (Reading)"),
        # Listening
        ("summarize_spoken_text", "Summarize Spoken Text"),
        ("l_mc_multiple", "MCQ – Multiple Answers (Listening)"),
        ("l_fill_in_blanks", "Fill in the Blanks (Listening)"),
        ("highlight_correct_summary", "Highlight Correct Summary"),
        ("l_mc_single", "MCQ – Single Answer (Listening)"),
        ("select_missing_word", "Select Missing Word"),
        ("highlight_incorrect_words", "Highlight Incorrect Words"),
        ("write_from_dictation", "Write from Dictation"),
    ]

    section = models.ForeignKey(
        "Section",
        on_delete=models.CASCADE,
        related_name="subsections",
        null=True,
        blank=True,
    )
    name = models.CharField(
        max_length=60, choices=SUBSECTION_CHOICES, default="read_aloud"
    )
    order = models.PositiveIntegerField(default=1)
    rubric = models.JSONField(default=dict, blank=True, null=True)
    trait_skill_map = models.JSONField(default=dict)
    instructions = models.TextField(blank=True, null=True)
    evaluation_type = models.CharField(
        max_length=10,
        choices=[
            ("rule", "Rule"),
            ("ai", "AI"),
        ],
        default="ai",
    )

    ai_input_type = models.CharField(
        max_length=10,
        choices=[
            ("text", "Text only"),
            ("audio", "transcription"),
        ],
        default="text",
    )
    # NEW FIELDS
    use_pronunciation = models.BooleanField(default=False)
    use_fluency = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.pk:
            _protect_active_session_question_config(
                Question.objects.filter(subsection_id=self.pk).values_list(
                    "pk",
                    flat=True,
                ),
                "Subsections",
            )
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.section.name} - {self.name}"


class Question(models.Model):
    """Question master table connected with subsection"""

    mock_test_section = models.ForeignKey(
        MockTestSection,
        on_delete=models.CASCADE,
        related_name="questions",
        null=True,
        blank=True,
    )
    QUESTION_TYPES = [
        ("single_answer", "Single Answer"),
        ("multiple_answer", "Multiple Answers"),
    ]
    DIFFICULTY_LEVELS = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    question_type = models.CharField(
        max_length=20, choices=QUESTION_TYPES, default="single"
    )
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_LEVELS, default="medium"
    )
    subsection = models.ForeignKey(
        SubSection,
        on_delete=models.CASCADE,
        related_name="questions",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100, null=True, blank=True)
    text = models.TextField(blank=True, null=True)
    audio = models.FileField(upload_to="questions/audio/", blank=True, null=True)
    image = models.FileField(upload_to="questions/images/", blank=True, null=True)
    correct_answer = models.TextField(blank=True, null=True)
    answer_explanation = models.TextField(
        blank=True,
        default="",
        help_text="Candidate-facing explanation shown after evaluation.",
    )
    answer_explanation_draft = models.TextField(
        blank=True,
        default="",
        help_text="AI-generated draft awaiting administrator review.",
    )
    reading_time = models.PositiveIntegerField(
        help_text="Time allowed to read question in seconds", default=0
    )
    answering_time = models.PositiveIntegerField(
        help_text="Time allowed to answer in seconds", default=0
    )
    speaking_score_max = models.FloatField(null=True, blank=True)
    writing_score_max = models.FloatField(null=True, blank=True)
    reading_score_max = models.FloatField(null=True, blank=True)
    listening_score_max = models.FloatField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.pk:
            _protect_active_session_question_config([self.pk], "Questions")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subsection.name} - Q{self.id}"


class SubQuestion(models.Model):
    """Represents each blank (or sub-question) in a fill-in-the-blank type question."""

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="sub_questions"
    )
    blank_number = models.PositiveIntegerField(help_text="Blank number (1,2,3...)")
    text_before_blank = models.TextField(blank=True, null=True)
    text_after_blank = models.TextField(blank=True, null=True)
    correct_answer = models.CharField(max_length=255, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.question_id:
            _protect_active_session_question_config(
                [self.question_id],
                "Sub-questions",
            )
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.question.name} - Blank {self.blank_number}"
    
    class Meta:
        ordering = ['blank_number']

class QuestionOption(models.Model):
    """Represents the options available for a question or a sub-question."""

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        null=True,
        blank=True,
    )
    sub_question = models.ForeignKey(
        SubQuestion,
        on_delete=models.CASCADE,
        related_name="options",
        null=True,
        blank=True,
        help_text="Used only for fill-in-the-blank type questions",
    )
    option_text = models.TextField(null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    order_position = models.PositiveIntegerField(null=True, blank=True)

    def save(self, *args, **kwargs):
        question_id = self.question_id
        if question_id is None and self.sub_question_id:
            question_id = SubQuestion.objects.filter(
                pk=self.sub_question_id,
            ).values_list("question_id", flat=True).first()
        if question_id:
            _protect_active_session_question_config([question_id], "Question options")
        return super().save(*args, **kwargs)

    def __str__(self):
        if self.sub_question:
            return f"Blank {self.sub_question.blank_number} - {self.option_text}"
        return f"{self.question} - {self.option_text}"


def _protect_active_session_question_config(question_ids, label):
    if not question_ids:
        return
    if SessionQuestion.objects.filter(
        question_id_snapshot__in=question_ids,
    ).exists():
        raise ValidationError(
            f"{label} used by a versioned exam session cannot be edited. "
            "Create a new mock-test version for future candidates."
        )


from django.db.models import Sum


class UserMockTestSession(models.Model):
    name = models.CharField(max_length=255)
    session_id = models.CharField(max_length=255)
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE)
    # new field required for pagination + skipping
    current_mocktest_section = models.ForeignKey(
        MockTestSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_mocktest_sections",
    )
    current_question_order = models.IntegerField(default=1)
    completed_sections = models.JSONField(default=list, blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    submission_completed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    manifest_version = models.CharField(max_length=32, blank=True, default="")
    mock_test_snapshot = models.JSONField(default=dict)
    expected_question_count = models.PositiveIntegerField(default=0)
    finalized_at = models.DateTimeField(blank=True, null=True)
    finalized_result_version = models.PositiveIntegerField(default=0)
    scoring_mode = models.CharField(
        max_length=10,
        choices=SCORING_MODE_CHOICES,
        default=default_session_scoring_mode,
        editable=False,
        help_text="Scoring rollout mode pinned when this exam session started.",
    )
    total_score = models.FloatField(default=0)
    speaking_score_awarded = models.FloatField(default=0)
    writing_score_awarded = models.FloatField(default=0)
    reading_score_awarded = models.FloatField(default=0)
    listening_score_awarded = models.FloatField(default=0)

    def evaluations_are_complete(self):
        if self.manifest_version:
            from mocktest.services.session_finalization import session_is_finalizable

            return session_is_finalizable(self.pk)
        responses = self.userresponse_set.all()
        if not responses.exists():
            return False
        return not responses.exclude(
            evaluated=True,
        ).exclude(
            evaluation_status="completed",
        ).exists()

    def sync_evaluation_completion(self):
        """Keep is_completed aligned with submission and evaluation state."""
        if self.manifest_version:
            from mocktest.services.session_finalization import recalculate_session_state

            was_completed = self.is_completed
            recalculate_session_state(self.pk)
            self.refresh_from_db()
            return self.is_completed != was_completed
        should_be_completed = bool(
            self.completed_at and self.evaluations_are_complete()
        )
        if self.is_completed == should_be_completed:
            return False

        self.is_completed = should_be_completed
        self.save(update_fields=["is_completed"])
        return True

    def mark_submission_completed(self):
        """Idempotently record that the candidate finished submitting the exam."""
        if self.manifest_version:
            from mocktest.services.session_finalization import complete_session_submission

            changed = self.submission_completed_at is None
            complete_session_submission(self.pk)
            self.refresh_from_db()
            return changed
        changed = self.completed_at is None
        if changed:
            self.completed_at = timezone.now()
            self.save(update_fields=["completed_at"])
        self.sync_evaluation_completion()
        return changed

    def mark_completed(self):
        """Compatibility alias for callers completing exam submission."""
        return self.mark_submission_completed()

    def aggregate_scores(self):
        """
        Aggregate all evaluated UserResponses into session-level skill scores.
        """

        if self.manifest_version:
            from mocktest.services.session_finalization import recalculate_session_state

            recalculate_session_state(self.pk)
            self.refresh_from_db()
            return

        qs = self.userresponse_set.filter(evaluated=True)

        aggregates = qs.aggregate(
            speaking=Sum("speaking_score_awarded"),
            writing=Sum("writing_score_awarded"),
            reading=Sum("reading_score_awarded"),
            listening=Sum("listening_score_awarded"),
        )

        self.speaking_score_awarded = aggregates["speaking"] or 0
        self.writing_score_awarded = aggregates["writing"] or 0
        self.reading_score_awarded = aggregates["reading"] or 0
        self.listening_score_awarded = aggregates["listening"] or 0

        overall_raw = self.calculate_overall_raw_score()

        # Optional: scale here or later
        self.total_score = overall_raw

        self.save(
            update_fields=[
                "speaking_score_awarded",
                "writing_score_awarded",
                "reading_score_awarded",
                "listening_score_awarded",
                "total_score",
            ]
        )
        self.sync_evaluation_completion()

    def calculate_overall_raw_score(self):
        qs = self.userresponse_set.filter(evaluated=True)

        speaking = sum(r.speaking_score_awarded for r in qs)
        writing = sum(r.writing_score_awarded for r in qs)
        reading = sum(r.reading_score_awarded for r in qs)
        listening = sum(r.listening_score_awarded for r in qs)

        raw_total = speaking + writing + reading + listening

        max_speaking = sum(r.question.speaking_score_max or 0 for r in qs)
        max_writing = sum(r.question.writing_score_max or 0 for r in qs)
        max_reading = sum(r.question.reading_score_max or 0 for r in qs)
        max_listening = sum(r.question.listening_score_max or 0 for r in qs)

        max_total = max_speaking + max_writing + max_reading + max_listening

        if max_total == 0:
            return 0

        normalized = (raw_total / max_total) * 90

        # tiny improvement
        normalized = min(normalized, 90)

        return round(normalized, 2)


def apply_response_skill_scores(response):
    from examinor.scoring.response_scores import (
        compile_response_score_evidence,
        promoted_skill_values,
        response_scoring_mode,
    )

    evidence = compile_response_score_evidence(
        response.question,
        response.evaluation_result,
        mode=response_scoring_mode(response),
    )
    promoted = promoted_skill_values(evidence)
    response.speaking_score_awarded = promoted["speaking"]
    response.writing_score_awarded = promoted["writing"]
    response.reading_score_awarded = promoted["reading"]
    response.listening_score_awarded = promoted["listening"]
    response.evaluated = True
    response.evaluation_status = "completed"
    response.evaluation_stage = "scoring"
    response.evaluation_error = ""
    response.evaluation_result = dict(response.evaluation_result)
    response.evaluation_result["scoring_evidence"] = evidence
    response.save(
        update_fields=[
            "speaking_score_awarded",
            "writing_score_awarded",
            "reading_score_awarded",
            "listening_score_awarded",
            "evaluated",
            "evaluation_status",
            "evaluation_stage",
            "evaluation_error",
            "evaluation_result",
        ]
    )
    return evidence


class UserResponse(models.Model):
    EVALUATION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("transcribing", "Transcribing"),
        ("evaluating", "Evaluating"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    user_session = models.ForeignKey("UserMockTestSession", on_delete=models.CASCADE)
    mock_test = models.ForeignKey("MockTest", on_delete=models.CASCADE)
    question = models.ForeignKey("Question", on_delete=models.PROTECT)

    answer_data = models.JSONField(
        default=dict, null=True, blank=True
    )  # Store any type of answer here
    answer_audio = models.FileField(upload_to="response/audio/", blank=True, null=True)
    transcribed_audio_data = models.JSONField(blank=True, null=True)
    speaking_score_awarded = models.FloatField(default=0)
    writing_score_awarded = models.FloatField(default=0)
    reading_score_awarded = models.FloatField(default=0)
    listening_score_awarded = models.FloatField(default=0)
    evaluated = models.BooleanField(default=False)
    evaluation_status = models.CharField(
        max_length=20,
        choices=EVALUATION_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    evaluation_stage = models.CharField(max_length=50, blank=True, default="")
    evaluation_error = models.TextField(blank=True, default="")
    evaluation_attempts = models.PositiveIntegerField(default=0)
    last_evaluation_attempt_at = models.DateTimeField(blank=True, null=True)
    evaluation_result = models.JSONField(default=dict, null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def apply_skill_scores(self):
        return apply_response_skill_scores(self)

    def __str__(self):
        return f"{self.user_session.name} - {self.mock_test} "

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_session", "question"],
                name="uniq_userresp_session_question",
            ),
        ]
        indexes = [
            models.Index(
                fields=["evaluation_status", "submitted_at"],
                name="userresp_status_submitted_idx",
            ),
            models.Index(
                fields=["evaluation_status", "last_evaluation_attempt_at"],
                name="userresp_status_attempt_idx",
            ),
            models.Index(
                fields=["mock_test", "submitted_at"],
                name="userresp_mock_submitted_idx",
            ),
            models.Index(
                fields=["user_session", "submitted_at"],
                name="userresp_session_submitted_idx",
            ),
        ]


class SessionQuestion(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("answered", "Answered"),
        ("skipped", "Skipped"),
        ("timed_out", "Timed out"),
        ("not_reached", "Not reached"),
    )

    session = models.ForeignKey(
        UserMockTestSession,
        on_delete=models.CASCADE,
        related_name="question_manifest",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="session_snapshots",
    )
    question_id_snapshot = models.PositiveBigIntegerField()
    order = models.PositiveIntegerField()
    mock_test_section_id_snapshot = models.PositiveBigIntegerField()
    section_name = models.CharField(max_length=100, blank=True, default="")
    section_order = models.PositiveIntegerField(default=0)
    subsection_name = models.CharField(max_length=60, blank=True, default="")
    subsection_order = models.PositiveIntegerField(default=0)
    expected_input_type = models.CharField(max_length=10, default="text")
    question_snapshot = models.JSONField(default=dict)
    rubric_snapshot = models.JSONField(default=dict)
    trait_skill_map_snapshot = models.JSONField(default=dict)
    skill_maxima_snapshot = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    response = models.OneToOneField(
        UserResponse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="session_question",
    )
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "question_id_snapshot"],
                name="uniq_session_question_snapshot",
            ),
            models.UniqueConstraint(
                fields=["session", "order"],
                name="uniq_session_question_order",
            ),
        ]
        indexes = [
            models.Index(
                fields=["session", "status", "order"],
                name="sessionq_status_order_idx",
            ),
        ]

    def __str__(self):
        return f"{self.session_id}:{self.order}:{self.question_id_snapshot}"


class SessionResult(models.Model):
    session = models.ForeignKey(
        UserMockTestSession,
        on_delete=models.CASCADE,
        related_name="result_versions",
    )
    version = models.PositiveIntegerField()
    engine_version = models.CharField(max_length=64)
    scoring_mode = models.CharField(max_length=10, choices=SCORING_MODE_CHOICES)
    expected_question_count = models.PositiveIntegerField()
    resolved_question_count = models.PositiveIntegerField()
    evaluated_response_count = models.PositiveIntegerField()
    skill_scores = models.JSONField(default=dict)
    overall_score = models.FloatField(default=0)
    response_snapshot = models.JSONField(default=list)
    content_hash = models.CharField(max_length=64)
    finalized_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["session_id", "version"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "version"],
                name="uniq_session_result_version",
            ),
            models.UniqueConstraint(
                fields=["session", "content_hash"],
                name="uniq_session_result_content",
            ),
        ]

    def __str__(self):
        return f"{self.session_id}:v{self.version}"


class SingleResponse(models.Model):
    EVALUATION_STATUS_CHOICES = UserResponse.EVALUATION_STATUS_CHOICES

    name = models.CharField(max_length=255, default="Single Response")
    question = models.ForeignKey("Question", on_delete=models.PROTECT)

    answer_data = models.JSONField(
        default=dict, null=True, blank=True
    )  # Store any type of answer here
    answer_audio = models.FileField(upload_to="response/audio/", blank=True, null=True)
    transcribed_audio_data = models.JSONField(blank=True, null=True)
    speaking_score_awarded = models.FloatField(default=0)
    writing_score_awarded = models.FloatField(default=0)
    reading_score_awarded = models.FloatField(default=0)
    listening_score_awarded = models.FloatField(default=0)
    evaluated = models.BooleanField(default=False)
    evaluation_status = models.CharField(
        max_length=20,
        choices=EVALUATION_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    evaluation_stage = models.CharField(max_length=50, blank=True, default="")
    evaluation_error = models.TextField(blank=True, default="")
    evaluation_attempts = models.PositiveIntegerField(default=0)
    last_evaluation_attempt_at = models.DateTimeField(blank=True, null=True)
    evaluation_result = models.JSONField(default=dict, null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def apply_skill_scores(self):
        return apply_response_skill_scores(self)

    def __str__(self):
        return f"{self.name} - {self.question} "

    class Meta:
        indexes = [
            models.Index(
                fields=["evaluation_status", "submitted_at"],
                name="singleresp_status_submit_idx",
            ),
            models.Index(
                fields=["evaluation_status", "last_evaluation_attempt_at"],
                name="singleresp_status_attempt_idx",
            ),
        ]


class EvaluationJob(models.Model):
    RESPONSE_TYPE_CHOICES = (
        ("user", "User response"),
        ("single", "Single response"),
    )
    STATUS_CHOICES = (
        ("waiting_dispatch", "Waiting for dispatch"),
        ("dispatched", "Dispatched"),
        ("processing", "Processing"),
        ("waiting_retry", "Waiting to retry"),
        ("completed", "Completed"),
        ("failed_permanent", "Permanently failed"),
        ("manual_review", "Manual review"),
    )

    response_type = models.CharField(max_length=10, choices=RESPONSE_TYPE_CHOICES)
    response_id = models.PositiveBigIntegerField()
    question_id = models.PositiveBigIntegerField()
    input_hash = models.CharField(max_length=64)
    engine_version = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=24,
        choices=STATUS_CHOICES,
        default="waiting_dispatch",
        db_index=True,
    )
    current_attempt = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    lease_owner = models.CharField(max_length=255, blank=True, default="")
    lease_expires_at = models.DateTimeField(blank=True, null=True)
    input_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.response_type}:{self.response_id} [{self.status}]"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "response_type",
                    "response_id",
                    "input_hash",
                    "engine_version",
                    "revision",
                ],
                name="uniq_evaluation_job_revision",
            ),
        ]
        indexes = [
            models.Index(
                fields=["response_type", "response_id", "-created_at"],
                name="evaljob_response_created_idx",
            ),
            models.Index(
                fields=["status", "available_at"],
                name="evaljob_status_available_idx",
            ),
        ]


class EvaluationAttempt(models.Model):
    job = models.ForeignKey(
        EvaluationJob,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    attempt_number = models.PositiveIntegerField()
    stage = models.CharField(max_length=50)
    task_id = models.CharField(max_length=255, blank=True, default="")
    provider = models.CharField(max_length=50, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")
    prompt_version = models.CharField(max_length=64, blank=True, default="")
    scoring_version = models.CharField(max_length=64, blank=True, default="")
    provider_request_id = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(blank=True, null=True)
    latency_ms = models.PositiveBigIntegerField(blank=True, null=True)
    input_snapshot = models.JSONField(default=dict)
    raw_result = models.JSONField(default=dict)
    normalized_result = models.JSONField(default=dict)
    error_category = models.CharField(max_length=50, blank=True, default="")
    error_code = models.CharField(max_length=100, blank=True, default="")
    error_detail = models.TextField(blank=True, default="")
    retryable = models.BooleanField(default=False)
    token_usage = models.JSONField(default=dict)
    estimated_cost = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"{self.job} attempt {self.attempt_number} ({self.stage})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "attempt_number"],
                name="uniq_evaluation_attempt_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["job", "-attempt_number"],
                name="evalattempt_job_number_idx",
            ),
        ]


class EvaluationOutbox(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        EvaluationJob,
        on_delete=models.CASCADE,
        related_name="outbox_events",
    )
    event_type = models.CharField(max_length=50, default="dispatch")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(blank=True, null=True)
    publish_attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    locked_at = models.DateTimeField(blank=True, null=True)
    lock_token = models.UUIDField(blank=True, null=True)

    def __str__(self):
        return f"{self.event_type}:{self.event_id}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "event_type"],
                condition=models.Q(published_at__isnull=True),
                name="uniq_unpublished_job_event",
            ),
        ]
        indexes = [
            models.Index(
                fields=["published_at", "created_at"],
                name="evaloutbox_publish_created_idx",
            ),
        ]


@receiver(pre_delete, sender=MockTestSection)
def protect_active_mock_test_section_delete(sender, instance, **kwargs):
    _protect_active_session_question_config(
        Question.objects.filter(mock_test_section=instance).values_list(
            "pk",
            flat=True,
        ),
        "Mock-test sections",
    )


@receiver(pre_delete, sender=SubSection)
def protect_active_subsection_delete(sender, instance, **kwargs):
    _protect_active_session_question_config(
        Question.objects.filter(subsection=instance).values_list("pk", flat=True),
        "Subsections",
    )


@receiver(pre_delete, sender=Question)
def protect_active_question_delete(sender, instance, **kwargs):
    _protect_active_session_question_config([instance.pk], "Questions")


@receiver(pre_delete, sender=SubQuestion)
def protect_active_subquestion_delete(sender, instance, **kwargs):
    _protect_active_session_question_config(
        [instance.question_id],
        "Sub-questions",
    )


@receiver(pre_delete, sender=QuestionOption)
def protect_active_question_option_delete(sender, instance, **kwargs):
    question_id = instance.question_id
    if question_id is None and instance.sub_question_id:
        question_id = SubQuestion.objects.filter(
            pk=instance.sub_question_id,
        ).values_list("question_id", flat=True).first()
    if question_id:
        _protect_active_session_question_config(
            [question_id],
            "Question options",
        )
