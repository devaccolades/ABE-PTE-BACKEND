import uuid
from django.db import models


class Skill(models.Model):
    SKILL_CHOICES = [
        ('speaking', 'Speaking'),
        ('writing', 'Writing'),
        ('reading', 'Reading'),
        ('listening', 'Listening'),
    ]
    name = models.CharField(max_length=50, choices=SKILL_CHOICES, unique=True)

    def __str__(self):
        return self.name


class ExamPart(models.Model):
    """
    Represents the actual structure of a PTE exam:
    e.g., Part 1: Speaking & Writing, Part 2: Reading, Part 3: Listening
    """
    name = models.CharField(max_length=100, unique=True)
    order = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Part {self.order}: {self.name}"


class Section(models.Model):
    """
    Main sections linked to both a Skill and an Exam Part.
    Example: Speaking section inside 'Part 1: Speaking & Writing'
    """
    exam_part = models.ForeignKey(ExamPart, on_delete=models.CASCADE, related_name='sections',null=True,blank=True)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='sections',null=True,blank=True)
    name = models.CharField(max_length=100,null=True,blank=True)
    total_duration = models.PositiveIntegerField(blank=True,null=True)
    

    def __str__(self):
        return f"{self.exam_part.name} - {self.skill.name} - {self.name}"

class SubSection(models.Model):
    """
    Detailed subsections like 'Read Aloud', 'Describe Image', etc.
    """
    section = models.ForeignKey('Section', on_delete=models.CASCADE, related_name='subsections',null=True,blank=True)
    name = models.CharField(max_length=150,null=True,blank=True)
    order = models.PositiveIntegerField(default=1)
    
    def __str__(self):
        return f"{self.section.name} - {self.name}"
    

class Question(models.Model):
    """Question master table connected with subsection"""
    subsection = models.ForeignKey(SubSection, on_delete=models.CASCADE, related_name='questions',null=True,blank=True)
    name = models.CharField(max_length=100,null=True,blank=True)
    text = models.TextField(blank=True, null=True)
    audio = models.FileField(upload_to='questions/audio/', blank=True, null=True)
    image = models.FileField(upload_to='questions/images/', blank=True, null=True)
    correct_answer = models.TextField(blank=True, null=True)
    reading_time = models.PositiveIntegerField(help_text="Time allowed to read question in seconds", default=0)
    answering_time = models.PositiveIntegerField(help_text="Time allowed to answer in seconds", default=0)
    speaking_score_max = models.FloatField(null=True,blank=True)
    writing_score_max = models.FloatField(null=True,blank=True)
    reading_score_max = models.FloatField(null=True,blank=True)
    listening_score_max = models.FloatField(null=True,blank=True)


    def __str__(self):
        return f"{self.subsection.name} - Q{self.id}"


class QuestionOptions(models.Model):
    """Represents the options available for a question (for MCQ type questions)."""
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='options',
        null=True,
        blank=True
    )
    option_text = models.CharField(max_length=255, null=True, blank=True)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.question} - {self.option_text}"

class MockTest(models.Model):
    test_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True,blank=True)
    total_score = models.PositiveIntegerField(default=0, help_text="Maximum total score for the test")
    total_duration = models.PositiveIntegerField(help_text="Duration in seconds",null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class MockTestSection(models.Model):
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name="sections",null=True,blank=True)
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="mock_test_sections",null=True,blank=True)
    order = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.mock_test.title} - {self.section.name}"

class UserMockTestSession(models.Model):
    name = models.CharField(max_length=255)
    session_id = models.CharField(max_length=255)
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    total_score = models.PositiveIntegerField(default=0)
    speaking_score_awarded = models.FloatField(default=0. )
    writing_score_awarded = models.FloatField(default=0)
    reading_score_awarded = models.FloatField(default=0)
    listening_score_awarded = models.FloatField(default=0)

    def __str__(self):
        return self.name

class UserResponse(models.Model):
    user_session = models.ForeignKey(UserMockTestSession, on_delete=models.CASCADE, related_name='responses')
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    text_response = models.TextField(blank=True, null=True)
    audio_response = models.FileField(blank=True, null=True)
    speaking_score_awarded = models.FloatField(default=0. )
    writing_score_awarded = models.FloatField(default=0)
    reading_score_awarded = models.FloatField(default=0)
    listening_score_awarded = models.FloatField(default=0)
    evaluated = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user_session.name


# class Section(models.Model):
#     SECTION_TYPES = [
#         ('speaking & writing','Speaking & Writing'),
#         ('reading','Reading'),
#         ('listening','Listening'),
#     ]

#     section_type = models.CharField(max_length=50,choices=SECTION_TYPES)
#     has_subsection = models.BooleanField(default=False)

#     def __str__(self):
#         return self.section_type
    
# class SubSection(models.Model):
#     section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='subsections')
#     name = models.CharField(max_length=255)
#     order = models.PositiveIntegerField()

#     def __str__(self):
#         return f"{self.section.section_type} - {self.name}"
    
# class MockTestSection(models.Model):
#     mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='mocktest_sections')
#     section = models.ForeignKey(Section, on_delete=models.CASCADE)
#     order = models.PositiveIntegerField()
#     total_score_for_section = models.PositiveIntegerField()
#     section_total_duration = models.DurationField()
#     per_question_timer = models.BooleanField(default=False)

#     class Meta:
#         unique_together = ('mock_test', 'section')

#     def __str__(self):
#         return f"{self.mock_test.title} - {self.section.section_type}"

# class MockTestSubSection(models.Model):
#     mock_section = models.ForeignKey(MockTestSection, on_delete=models.CASCADE, related_name='subsections')
#     subsection = models.ForeignKey(SubSection, on_delete=models.CASCADE)
#     total_score_for_subsection = models.PositiveIntegerField()
#     total_duration = models.DurationField()
#     per_question_timer = models.BooleanField(default=False)

#     class Meta:
#         unique_together = ('mock_section', 'subsection')

#     def __str__(self):
#         return f"{self.mock_section} - {self.subsection.name}"



# class Question(models.Model):
#     QUESTION_TYPES = [
#             # Speaking & Writing
#             ('read_aloud', 'Read Aloud'),
#             ('repeat_sentence', 'Repeat Sentence'),
#             ('describe_image', 'Describe Image'),
#             ('retell_lecture', 'Re-tell Lecture'),
#             ('answer_short_question', 'Answer Short Question'),
#             ('summarize_written_text', 'Summarize Written Text'),
#             ('write_essay', 'Write Essay'),

#             # Reading
#             ('reading_writing_fill_blanks', 'Reading & Writing: Fill in the Blanks'),
#             ('reading_mcq_single', 'Reading MCQ: Single Answer'),
#             ('reading_mcq_multiple', 'Reading MCQ: Multiple Answers'),
#             ('reorder_paragraphs', 'Re-order Paragraphs'),
#             ('reading_fill_blanks', 'Reading: Fill in the Blanks'),

#             # Listening
#             ('summarize_spoken_text', 'Summarize Spoken Text'),
#             ('listening_mcq_multiple', 'Listening MCQ: Multiple Answers'),
#             ('listening_fill_blanks', 'Listening: Fill in the Blanks'),
#             ('highlight_correct_summary', 'Highlight Correct Summary'),
#             ('listening_mcq_single', 'Listening MCQ: Single Answer'),
#             ('select_missing_word', 'Select Missing Word'),
#             ('highlight_incorrect_words', 'Highlight Incorrect Words'),
#             ('write_from_dictation', 'Write from Dictation'),
#     ]
#     section = models.ForeignKey(Section, on_delete=models.CASCADE)
#     question_type = models.CharField(max_length=50,choices=QUESTION_TYPES, help_text="")
#     instructions = models.TextField(null=True, blank=True)
#     question_text = models.TextField(null=True, blank=True)
#     audio_file = models.FileField(blank=True, null=True)
#     image_file = models.FileField(blank=True, null=True)
#     correct_answer = models.TextField(blank=True, null=True)
#     options = models.JSONField(blank=True, null=True)
#     answering_time = models.PositiveIntegerField(help_text="how much Seconds allowed to answer")
#     is_first_listening_question = models.BooleanField(default=False)
#     subsection = models.ForeignKey(SubSection, on_delete=models.SET_NULL, blank=True, null=True)
#     reading_time = models.PositiveIntegerField(blank=True, null=True)

#     def __str__(self):
#         return f"{self.question_type} - {self.id}"

# class MockTestQuestion(models.Model):
#     mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE)
#     section = models.ForeignKey(Section, on_delete=models.CASCADE)
#     sub_section = models.ForeignKey(SubSection, on_delete=models.SET_NULL, null=True, blank=True)
#     question = models.ForeignKey(Question, on_delete=models.CASCADE)
#     order = models.PositiveIntegerField()
#     score_for_question = models.PositiveIntegerField()

#     class Meta:
#         unique_together = ('mock_test', 'section', 'question')


# class UserMockTestSession(models.Model):
#     name = models.CharField(max_length=255)
#     session_id = models.CharField(max_length=255)
#     mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE)
#     started_at = models.DateTimeField(auto_now_add=True)
#     completed_at = models.DateTimeField(blank=True, null=True)
#     is_completed = models.BooleanField(default=False)
#     total_score = models.PositiveIntegerField(default=0)


