from django import forms
from .models import Question
from .services.question_config import expected_question_skill_maxima


class QuestionAdminForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        subsection = cleaned.get("subsection")
        mock_test_section = cleaned.get("mock_test_section")

        if (
            subsection
            and mock_test_section
            and subsection.section_id != mock_test_section.section_id
        ):
            raise forms.ValidationError(
                "The question subsection and mock-test section must belong to the same section."
            )

        if subsection:
            for skill, maximum in expected_question_skill_maxima(subsection).items():
                field = f"{skill}_score_max"
                if not cleaned.get(field):
                    cleaned[field] = maximum

        return cleaned
