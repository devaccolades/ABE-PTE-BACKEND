import uuid
from django.db import models
from django.utils import timezone
import logging

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


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

    def save(self, *args, **kwargs):
        if self._is_being_activated() and not getattr(
            self, "_publication_validation_passed", False
        ):
            if not self.pk:
                raise ValidationError(
                    {"is_active": "Save the mock test as a draft before activating it."}
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
                    {"is_active": f"Mock test cannot be activated. {details}"}
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

    def __str__(self):
        if self.sub_question:
            return f"Blank {self.sub_question.blank_number} - {self.option_text}"
        return f"{self.question} - {self.option_text}"


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
    completed_at = models.DateTimeField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    total_score = models.FloatField(default=0)
    speaking_score_awarded = models.FloatField(default=0)
    writing_score_awarded = models.FloatField(default=0)
    reading_score_awarded = models.FloatField(default=0)
    listening_score_awarded = models.FloatField(default=0)

    def evaluations_are_complete(self):
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
    question = models.ForeignKey("Question", on_delete=models.CASCADE)

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

    def _normalize(self, raw, max_value, skill_name=None):
        """
        Skill normalization per-question.

        Rules:
        - NULL / 0 max  → skill not evaluated → force 0 (log warning)
        - Else          → cap raw score to max
        """
        if not max_value:
            if raw > 0:
                logger.warning(
                    "[SCORING-IGNORE] "
                    f"Question={self.question.id} | "
                    f"Subsection={self.question.subsection.name} | "
                    f"Skill={skill_name} | "
                    f"RawScore={raw} | "
                    f"MaxScore={max_value}"
                )
            return 0

        return min(raw, max_value)

    def apply_skill_scores(self):
        """
        Aggregate evaluation_result into skill scores
        using the question subsection's trait_skill_map.

        PTE RULE:
        - If a gate trait (content/form) EXISTS and its score == 0
        → entire question scores 0
        """

        if not self.evaluation_result:
            return

        scores = self.evaluation_result.get("evaluation", {}).get("scores", {})

        if not scores:
            return

        trait_skill = self.question.subsection.trait_skill_map or {}

        # ----------------------------
        # 1️⃣ GATE TRAIT SHORT-CIRCUIT
        # ----------------------------
        for gate_trait in ("content", "form"):
            if gate_trait in scores:
                gate_score = scores[gate_trait].get("score")
                if gate_score == 0:
                    # HARD STOP — model-safe
                    self.speaking_score_awarded = 0
                    self.writing_score_awarded = 0
                    self.reading_score_awarded = 0
                    self.listening_score_awarded = 0
                    self.evaluated = True
                    self.evaluation_status = "completed"
                    self.evaluation_stage = "scoring"
                    self.evaluation_error = ""

                    self.save(
                        update_fields=[
                            "speaking_score_awarded",
                            "writing_score_awarded",
                            "reading_score_awarded",
                            "listening_score_awarded",
                            "evaluated",
                            "evaluation_status",
                            "evaluation_stage",
                            "evaluation_error",
                        ]
                    )
                    return

        # ----------------------------
        # 2️⃣ NORMAL TRAIT → SKILL FLOW
        # ----------------------------

        # Reset AFTER gate check (important)
        self.speaking_score_awarded = 0
        self.writing_score_awarded = 0
        self.reading_score_awarded = 0
        self.listening_score_awarded = 0

        for component, payload in scores.items():
            value = payload.get("score")

            if value is None:
                continue

            for skill in trait_skill.get(component, []):
                if skill == "speaking":
                    self.speaking_score_awarded += value
                elif skill == "writing":
                    self.writing_score_awarded += value
                elif skill == "reading":
                    self.reading_score_awarded += value
                elif skill == "listening":
                    self.listening_score_awarded += value

        # ----------------------------
        # 3️⃣ NORMALISATION STEP (NEW)
        # ----------------------------

        q = self.question

        self.speaking_score_awarded = self._normalize(
            self.speaking_score_awarded, q.speaking_score_max, "speaking"
        )

        self.writing_score_awarded = self._normalize(
            self.writing_score_awarded, q.writing_score_max, "writing"
        )

        self.reading_score_awarded = self._normalize(
            self.reading_score_awarded, q.reading_score_max, "reading"
        )

        self.listening_score_awarded = self._normalize(
            self.listening_score_awarded, q.listening_score_max, "listening"
        )

        self.evaluated = True
        self.evaluation_status = "completed"
        self.evaluation_stage = "scoring"
        self.evaluation_error = ""
        self.save(
            update_fields=[
                "speaking_score_awarded",
                "writing_score_awarded",
                "reading_score_awarded",
                "listening_score_awarded",
                "evaluated",
                "evaluation_status",
                "evaluation_stage",
                "evaluation_error",
            ]
        )

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


class SingleResponse(models.Model):
    EVALUATION_STATUS_CHOICES = UserResponse.EVALUATION_STATUS_CHOICES

    name = models.CharField(max_length=255, default="Single Response")
    question = models.ForeignKey("Question", on_delete=models.CASCADE)

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

    def _normalize(self, raw, max_value, skill_name=None):
        """
        Skill normalization per-question.

        Rules:
        - NULL / 0 max  → skill not evaluated → force 0 (log warning)
        - Else          → cap raw score to max
        """
        if not max_value:
            if raw > 0:
                logger.warning(
                    "[SCORING-IGNORE] "
                    f"Question={self.question.id} | "
                    f"Subsection={self.question.subsection.name} | "
                    f"Skill={skill_name} | "
                    f"RawScore={raw} | "
                    f"MaxScore={max_value}"
                )
            return 0

        return min(raw, max_value)

    def apply_skill_scores(self):
        """
        Aggregate evaluation_result into skill scores
        using the question subsection's trait_skill_map.

        PTE RULE:
        - If a gate trait (content/form) EXISTS and its score == 0
        → entire question scores 0
        """

        if not self.evaluation_result:
            return

        scores = self.evaluation_result.get("evaluation", {}).get("scores", {})

        if not scores:
            return

        trait_skill = self.question.subsection.trait_skill_map or {}

        # ----------------------------
        # 1️⃣ GATE TRAIT SHORT-CIRCUIT
        # ----------------------------
        for gate_trait in ("content", "form"):
            if gate_trait in scores:
                gate_score = scores[gate_trait].get("score")
                if gate_score == 0:
                    # HARD STOP — model-safe
                    self.speaking_score_awarded = 0
                    self.writing_score_awarded = 0
                    self.reading_score_awarded = 0
                    self.listening_score_awarded = 0
                    self.evaluated = True
                    self.evaluation_status = "completed"
                    self.evaluation_stage = "scoring"
                    self.evaluation_error = ""

                    self.save(
                        update_fields=[
                            "speaking_score_awarded",
                            "writing_score_awarded",
                            "reading_score_awarded",
                            "listening_score_awarded",
                            "evaluated",
                            "evaluation_status",
                            "evaluation_stage",
                            "evaluation_error",
                        ]
                    )
                    return

        # ----------------------------
        # 2️⃣ NORMAL TRAIT → SKILL FLOW
        # ----------------------------

        # Reset AFTER gate check (important)
        self.speaking_score_awarded = 0
        self.writing_score_awarded = 0
        self.reading_score_awarded = 0
        self.listening_score_awarded = 0

        for component, payload in scores.items():
            value = payload.get("score")

            if value is None:
                continue

            for skill in trait_skill.get(component, []):
                if skill == "speaking":
                    self.speaking_score_awarded += value
                elif skill == "writing":
                    self.writing_score_awarded += value
                elif skill == "reading":
                    self.reading_score_awarded += value
                elif skill == "listening":
                    self.listening_score_awarded += value

        # ----------------------------
        # 3️⃣ NORMALISATION STEP (NEW)
        # ----------------------------

        q = self.question

        self.speaking_score_awarded = self._normalize(
            self.speaking_score_awarded, q.speaking_score_max, "speaking"
        )

        self.writing_score_awarded = self._normalize(
            self.writing_score_awarded, q.writing_score_max, "writing"
        )

        self.reading_score_awarded = self._normalize(
            self.reading_score_awarded, q.reading_score_max, "reading"
        )

        self.listening_score_awarded = self._normalize(
            self.listening_score_awarded, q.listening_score_max, "listening"
        )

        self.evaluated = True
        self.evaluation_status = "completed"
        self.evaluation_stage = "scoring"
        self.evaluation_error = ""
        self.save(
            update_fields=[
                "speaking_score_awarded",
                "writing_score_awarded",
                "reading_score_awarded",
                "listening_score_awarded",
                "evaluated",
                "evaluation_status",
                "evaluation_stage",
                "evaluation_error",
            ]
        )

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
