from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import EvaluationCache


@admin.register(EvaluationCache)
class EvaluationCacheAdmin(ModelAdmin):
    list_display = ("prompt_hash", "model", "created_at")
    list_filter = ("model", "created_at")
    search_fields = ("prompt_hash", "model")
    readonly_fields = ("prompt_hash", "model", "result", "created_at")
    ordering = ("-created_at",)
    list_fullwidth = True
    list_filter_submit = True

    def has_add_permission(self, request):
        return False
