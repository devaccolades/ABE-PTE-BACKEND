from django.db import transaction

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    SubQuestion,
)


@transaction.atomic
def create_editable_mock_test_copy(source):
    """Copy a question paper into a safe, inactive draft for editing."""
    draft = MockTest.objects.create(
        title=_available_copy_title(source.title),
        description=source.description,
        total_score=source.total_score,
        total_duration=source.total_duration,
        is_active=False,
        scoring_mode="v2",
    )

    sections = source.sections.select_related("section").order_by("order", "pk")
    for source_section in sections:
        draft_section = MockTestSection.objects.create(
            mock_test=draft,
            section=source_section.section,
            order=source_section.order,
            total_duration=source_section.total_duration,
        )
        questions = source_section.questions.select_related("subsection").order_by("pk")
        for source_question in questions:
            _copy_question(source_question, draft_section)

    return draft


def _copy_question(source, draft_section):
    question = Question.objects.create(
        mock_test_section=draft_section,
        question_type=source.question_type,
        difficulty=source.difficulty,
        subsection=source.subsection,
        name=source.name,
        text=source.text,
        audio=source.audio.name if source.audio else None,
        image=source.image.name if source.image else None,
        correct_answer=source.correct_answer,
        answer_explanation=source.answer_explanation,
        answer_explanation_draft=source.answer_explanation_draft,
        reading_time=source.reading_time,
        answering_time=source.answering_time,
        speaking_score_max=source.speaking_score_max,
        writing_score_max=source.writing_score_max,
        reading_score_max=source.reading_score_max,
        listening_score_max=source.listening_score_max,
    )

    direct_options = source.options.order_by("pk")
    QuestionOption.objects.bulk_create([
        QuestionOption(
            question=question,
            option_text=option.option_text,
            is_correct=option.is_correct,
            order_position=option.order_position,
        )
        for option in direct_options
    ])

    for source_blank in source.sub_questions.prefetch_related("options").order_by(
        "blank_number", "pk"
    ):
        blank = SubQuestion.objects.create(
            question=question,
            blank_number=source_blank.blank_number,
            text_before_blank=source_blank.text_before_blank,
            text_after_blank=source_blank.text_after_blank,
            correct_answer=source_blank.correct_answer,
        )
        QuestionOption.objects.bulk_create([
            QuestionOption(
                sub_question=blank,
                option_text=option.option_text,
                is_correct=option.is_correct,
                order_position=option.order_position,
            )
            for option in source_blank.options.order_by("pk")
        ])


def _available_copy_title(source_title):
    base = f"{source_title} - editable copy"
    title = base[:255]
    number = 2
    while MockTest.objects.filter(title=title).exists():
        suffix = f" {number}"
        title = f"{base[:255 - len(suffix)]}{suffix}"
        number += 1
    return title
