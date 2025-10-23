import uuid
from django.db import models


class MockTest(models.Model):
    test_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True,blank=True)
    total_score = models.PositiveIntegerField(default=0, help_text="Maximum total score for the test")
    total_duration = models.PositiveIntegerField(help_text="Duration in seconds")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class Section(models.Model):
    SECTION_TYPES = [
        ('speaking & writing','Speaking & Writing'),
        ('reading','Reading'),
        ('listening','Listening'),
    ]

    section_type = models.CharField(max_length=50,choices=SECTION_TYPES)
    has_subsection = models.BooleanField(default=False)

    def __str__(self):
        return self.section_type
    
class SubSection(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='subsections')
    name = models.CharField(max_length=255)
    order = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.section.section_type} - {self.name}"
    
class MockTestSection(models.Model):
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='mocktest_sections')
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    total_score_for_section = models.PositiveIntegerField()
    section_total_duration = models.DurationField()
    per_question_timer = models.BooleanField(default=False)

    class Meta:
        unique_together = ('mock_test', 'section')

    def __str__(self):
        return f"{self.mock_test.title} - {self.section.section_type}"

class Question(models.Model):

    QUESTION_TYPES = [
            # Speaking & Writing
            ('read_aloud', 'Read Aloud'),
            ('repeat_sentence', 'Repeat Sentence'),
            ('describe_image', 'Describe Image'),
            ('retell_lecture', 'Re-tell Lecture'),
            ('answer_short_question', 'Answer Short Question'),
            ('summarize_written_text', 'Summarize Written Text'),
            ('write_essay', 'Write Essay'),

            # Reading
            ('reading_writing_fill_blanks', 'Reading & Writing: Fill in the Blanks'),
            ('reading_mcq_single', 'Reading MCQ: Single Answer'),
            ('reading_mcq_multiple', 'Reading MCQ: Multiple Answers'),
            ('reorder_paragraphs', 'Re-order Paragraphs'),
            ('reading_fill_blanks', 'Reading: Fill in the Blanks'),

            # Listening
            ('summarize_spoken_text', 'Summarize Spoken Text'),
            ('listening_mcq_multiple', 'Listening MCQ: Multiple Answers'),
            ('listening_fill_blanks', 'Listening: Fill in the Blanks'),
            ('highlight_correct_summary', 'Highlight Correct Summary'),
            ('listening_mcq_single', 'Listening MCQ: Single Answer'),
            ('select_missing_word', 'Select Missing Word'),
            ('highlight_incorrect_words', 'Highlight Incorrect Words'),
            ('write_from_dictation', 'Write from Dictation'),
    ]
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    question_type = models.CharField(max_length=50,choices=QUESTION_TYPES)
    question_text = models.TextField()
    audio_file = models.FileField(blank=True, null=True)
    image_file = models.FileField(blank=True, null=True)
    correct_answer = models.JSONField(blank=True, null=True)
    options = models.JSONField(blank=True, null=True)
    answering_time = models.PositiveIntegerField(help_text="how much Seconds allowed to answer")
    is_first_listening_question = models.BooleanField(default=False)
    subsection = models.ForeignKey(SubSection, on_delete=models.SET_NULL, blank=True, null=True)
    reading_time = models.PositiveIntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.question_type} - {self.id}"
