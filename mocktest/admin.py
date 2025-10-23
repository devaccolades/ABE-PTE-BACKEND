from django.contrib import admin
from .models import MockTest, Section,SubSection,Question



@admin.register(MockTest)
class MockTestAdmin(admin.ModelAdmin):
    list_display = ('title', 'total_duration', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'description')
    ordering = ('-created_at',)
    # inlines = [MockTestSectionInline]
    list_per_page = 10

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('section_type', 'has_subsection')
    list_filter = ('section_type', 'has_subsection')
    search_fields = ('section_type',)
    # inlines = [SubSectionInline]


@admin.register(SubSection)
class SubSectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'section', 'order')
    list_filter = ('section',)
    search_fields = ('name',)
    ordering = ('section', 'order')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'section', 'question_type', 'is_first_listening_question', 'answering_timer')
    list_filter = ('section', 'question_type', 'is_first_listening_question')
    search_fields = ('question_text',)
    ordering = ('section', 'id')
    readonly_fields = ('id',)
    fieldsets = (
        ('Basic Info', {
            'fields': ('section', 'subsection', 'question_type', 'question_text')
        }),
        ('Media', {
            'fields': ('audio_file', 'image_file')
        }),
        ('Answer & Options', {
            'fields': ('correct_answer', 'options')
        }),
        ('Timing', {
            'fields': ('answering_timer', 'is_first_listening_question', 'read_time')
        }),
    )