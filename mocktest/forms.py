from django import forms
from django.urls import reverse
from django.utils.html import format_html

from .models import MockTest, Question
from .services.question_bank_validation import publication_errors


class MockTestAdminForm(forms.ModelForm):
    class Meta:
        model = MockTest
        exclude = ("test_id",)
        labels = {
            "is_active": "Available to candidates",
        }
        help_texts = {
            "is_active": (
                "Leave this off while preparing the question paper. Turn it on "
                "when the paper is ready; any missing setup will be listed below."
            ),
        }

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
            raise forms.ValidationError(self._publication_error_details(errors))

        self.instance._publication_validation_passed = True
        return True

    def clean_scoring_mode(self):
        scoring_mode = self.cleaned_data.get("scoring_mode", "shadow")
        if scoring_mode != "v2":
            return scoring_mode

        is_active = self.cleaned_data.get("is_active", self.instance.is_active)
        if not is_active:
            return scoring_mode
        if not self.instance.pk:
            raise forms.ValidationError(
                "Save and validate the mock test before enabling V2."
            )

        errors = publication_errors(self.instance)
        if errors:
            raise forms.ValidationError(self._publication_error_details(errors))

        self.instance._publication_validation_passed = True
        return scoring_mode

    @classmethod
    def _publication_error_details(cls, errors):
        details = [
            format_html(
                "This question paper is not ready to publish yet. "
                "Please correct the {} item(s) below and try again.",
                len(errors),
            )
        ]
        details.extend(cls._format_publication_error(issue) for issue in errors[:10])
        if len(errors) > 10:
            details.append(
                f"There are {len(errors) - 10} more item(s) to correct."
            )
        return details

    @staticmethod
    def _format_publication_error(issue):
        code = issue.get("code", "")
        problem = str(issue.get("problem") or "")

        if code == "missing_question_skill_max":
            skill = next(
                (
                    name
                    for name in ("speaking", "writing", "reading", "listening")
                    if f"awards {name}" in problem.lower()
                ),
                "required skill",
            )
            guidance = (
                f"Score setup is incomplete. Enter the maximum {skill.title()} "
                "score this question can award."
            )
        elif code == "invalid_answer_key" and "visible blank" in problem.lower():
            guidance = (
                "Blank setup is incomplete. Add the missing blanks to the passage "
                "and make sure every blank has one correct answer."
            )
        elif code in {"missing_image", "missing_image_file"}:
            guidance = "The question image is missing. Upload the required image."
        elif code in {"missing_audio", "missing_audio_file"}:
            guidance = "The question audio is missing. Upload the required audio."
        elif code == "invalid_answer_key":
            guidance = f"Answer setup is incomplete. {problem}"
        else:
            guidance = f"Question setup needs attention. {problem}"

        question_id = issue.get("question_id")
        question_name = issue.get("question_name") or "Unnamed question"
        if not question_id:
            return guidance

        question_url = reverse("admin:mocktest_question_change", args=[question_id])
        return format_html(
            "{} <a href=\"{}\"><strong>Open question {} ({})</strong></a>",
            guidance,
            question_url,
            question_id,
            question_name,
        )


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

        return cleaned
