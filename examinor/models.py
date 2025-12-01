from django.db import models

# Create your models here.

class EvaluationCache(models.Model):
    prompt_hash = models.CharField(max_length=64, unique=True)
    result = models.JSONField()  # full JSON result from evaluation
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.prompt_hash
