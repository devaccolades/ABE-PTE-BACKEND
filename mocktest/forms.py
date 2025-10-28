from django import forms
from .models import Question

TIME_UNIT_CHOICES = [
    ('seconds', 'Seconds'),
    ('minutes', 'Minutes'),
    ('hours', 'Hours'),
]

class QuestionAdminForm(forms.ModelForm):
    reading_time_value = forms.FloatField(label="Reading Time", required=False)
    reading_time_unit = forms.ChoiceField(choices=TIME_UNIT_CHOICES, initial='seconds', required=False)

    answering_time_value = forms.FloatField(label="Answering Time", required=False)
    answering_time_unit = forms.ChoiceField(choices=TIME_UNIT_CHOICES, initial='seconds', required=False)

    class Meta:
        model = Question
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Prefill the values in correct unit (convert seconds → min/hr)
        if self.instance and self.instance.reading_time:
            self.fields['reading_time_value'].initial = self.instance.reading_time
            self.fields['reading_time_unit'].initial = 'seconds'
        if self.instance and self.instance.answering_time:
            self.fields['answering_time_value'].initial = self.instance.answering_time
            self.fields['answering_time_unit'].initial = 'seconds'

    def clean(self):
        cleaned_data = super().clean()
        rt_value = cleaned_data.get('reading_time_value') or 0
        rt_unit = cleaned_data.get('reading_time_unit') or 'seconds'
        at_value = cleaned_data.get('answering_time_value') or 0
        at_unit = cleaned_data.get('answering_time_unit') or 'seconds'

        def to_seconds(value, unit):
            if unit == 'minutes':
                return int(value * 60)
            elif unit == 'hours':
                return int(value * 3600)
            return int(value)

        cleaned_data['reading_time'] = to_seconds(rt_value, rt_unit)
        cleaned_data['answering_time'] = to_seconds(at_value, at_unit)
        return cleaned_data
