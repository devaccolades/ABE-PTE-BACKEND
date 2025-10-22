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

    section_types = models.CharField(max_length=50,choices=SECTION_TYPES)
    has_subsection = models.BooleanField(default=False)

    def __str__(self):
        return self.section_type