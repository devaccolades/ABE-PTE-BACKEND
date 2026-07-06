from django.db import models

# Create your models here.

class EvaluationCache(models.Model):
    prompt_hash = models.CharField(max_length=64, db_index=True)
    model = models.CharField(max_length=100, default="gpt-5-nano", db_index=True)
    result = models.JSONField()  # full JSON result from evaluation
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.model}:{self.prompt_hash}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["prompt_hash", "model"],
                name="unique_evaluation_cache_prompt_model",
            )
        ]
