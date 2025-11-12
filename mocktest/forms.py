from django import forms
from django.contrib import admin
from .models import Question


class QuestionAdminForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ordered and grouped choices with section names
        ordered_choices = [
            # Speaking
            ("read_aloud", "Speaking – Read Aloud"),
            ("repeat_sentence", "Speaking – Repeat Sentence"),
            ("describe_image", "Speaking – Describe an Image"),
            ("retell_lecture", "Speaking – Retell a Lecture"),
            ("answer_short_question", "Speaking – Answer a Short Question"),
            ("summarise_group_discussion", "Speaking – Summarize a Group Discussion"),
            ("respond_to_a_situation", "Speaking – Respond to a Situation"),

            # Writing
            ("summarize_written_text", "Writing – Summarize Written Text"),
            ("write_essay", "Writing – Write an Essay"),

            # Reading
            ("fib_dropdown", "Reading – Fill in the Blanks (Dropdown)"),
            ("mc_multiple", "Reading – Multiple Choice – Multiple Answers"),
            ("reorder_paragraphs", "Reading – Reorder Paragraphs"),
            ("fib_drag_drop", "Reading – Fill in the Blanks (Drag & Drop)"),
            ("mc_single", "Reading – Multiple Choice – Single Answer"),

            # Listening
            ("summarize_spoken_text", "Listening – Summarize Spoken Text"),
            ("l_mc_multiple", "Listening – Multiple Choice – Multiple Answers"),
            ("l_fill_in_blanks", "Listening – Fill in the Blanks"),
            ("highlight_correct_summary", "Listening – Highlight Correct Summary"),
            ("l_mc_single", "Listening – Multiple Choice – Single Answer"),
            ("select_missing_word", "Listening – Select the Missing Word"),
            ("highlight_incorrect_words", "Listening – Highlight Incorrect Words"),
            ("write_from_dictation", "Listening – Write from Dictation"),
        ]

        # Assign reordered and renamed choices
        self.fields["subsection"].choices = ordered_choices
