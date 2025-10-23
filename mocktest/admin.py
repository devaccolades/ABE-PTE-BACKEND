from django.contrib import admin
from .models import MockTest, Section,SubSection



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