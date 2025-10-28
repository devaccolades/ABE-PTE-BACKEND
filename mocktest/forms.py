from django.contrib import admin
from django import forms
from .models import Question

# Time unit choices
TIME_UNIT_CHOICES = [
    ('seconds', 'Seconds'),
    ('minutes', 'Minutes'),
    ('hours', 'Hours'),
]


class QuestionAdminForm(forms.ModelForm):
    # Custom fields for better UX
    reading_time_value = forms.FloatField(label="Reading Time", required=False)
    reading_time_unit = forms.ChoiceField(choices=TIME_UNIT_CHOICES, initial='seconds', required=False)

    answering_time_value = forms.FloatField(label="Answering Time", required=False)
    answering_time_unit = forms.ChoiceField(choices=TIME_UNIT_CHOICES, initial='seconds', required=False)

    class Meta:
        model = Question
        exclude = ('reading_time', 'answering_time')  # hide raw fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Prefill values when editing
        if self.instance and self.instance.reading_time:
            seconds = self.instance.reading_time
            # Display in best fit unit (seconds/minutes/hours)
            if seconds >= 3600:
                self.fields['reading_time_value'].initial = round(seconds / 3600, 2)
                self.fields['reading_time_unit'].initial = 'hours'
            elif seconds >= 60:
                self.fields['reading_time_value'].initial = round(seconds / 60, 2)
                self.fields['reading_time_unit'].initial = 'minutes'
            else:
                self.fields['reading_time_value'].initial = seconds
                self.fields['reading_time_unit'].initial = 'seconds'

        if self.instance and self.instance.answering_time:
            seconds = self.instance.answering_time
            if seconds >= 3600:
                self.fields['answering_time_value'].initial = round(seconds / 3600, 2)
                self.fields['answering_time_unit'].initial = 'hours'
            elif seconds >= 60:
                self.fields['answering_time_value'].initial = round(seconds / 60, 2)
                self.fields['answering_time_unit'].initial = 'minutes'
            else:
                self.fields['answering_time_value'].initial = seconds
                self.fields['answering_time_unit'].initial = 'seconds'

    def clean(self):
        cleaned_data = super().clean()

        def to_seconds(value, unit):
            if not value:
                return 0
            if unit == 'minutes':
                return int(value * 60)
            elif unit == 'hours':
                return int(value * 3600)
            return int(value)

        cleaned_data['reading_time'] = to_seconds(
            cleaned_data.get('reading_time_value'),
            cleaned_data.get('reading_time_unit')
        )
        cleaned_data['answering_time'] = to_seconds(
            cleaned_data.get('answering_time_value'),
            cleaned_data.get('answering_time_unit')
        )

        return cleaned_data