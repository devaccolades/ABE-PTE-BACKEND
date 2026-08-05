from django import forms
from .models import MockTest, Question
from .services.question_config import expected_question_skill_maxima
from .services.question_bank_validation import publication_errors


class MockTestAdminForm(forms.ModelForm):
    class Meta:
        model = MockTest
        exclude = ("test_id",)

    def clean_is_active(self):
        is_active = self.cleaned_data.get("is_active", False)
        if not is_active:
            return False

        if not self.instance.pk:
            raise forms.ValidationError(
                "Save the mock test as a draft, add its sections and questions, then activate it."
            )

        was_active = MockTest.objects.filter(pk=self.instance.pk).values_list(
            "is_active", flat=True
        ).first()
        if was_active:
            return True

        errors = publication_errors(self.instance)
        if errors:
            details = [
                self._format_publication_error(issue) for issue in errors[:10]
            ]
            if len(errors) > 10:
                details.append(f"And {len(errors) - 10} more error(s).")
            raise forms.ValidationError(details)

        self.instance._publication_validation_passed = True
        return True

    @staticmethod
    def _format_publication_error(issue):
        question = (
            f"Question {issue['question_id']} ({issue['question_name']}): "
            if issue["question_id"]
            else ""
        )
        return f"{question}{issue['problem']} Fix: {issue['manual_fix']}"


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
