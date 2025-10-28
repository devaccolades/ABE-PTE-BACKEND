class QuestionAdminForm(forms.ModelForm):
    reading_time_value = forms.FloatField(label="Reading Time", required=False)
    reading_time_unit = forms.ChoiceField(choices=TIME_UNIT_CHOICES, initial='seconds', required=False)

    answering_time_value = forms.FloatField(label="Answering Time", required=False)
    answering_time_unit = forms.ChoiceField(choices=TIME_UNIT_CHOICES, initial='seconds', required=False)

    class Meta:
        model = Question
        exclude = ('reading_time', 'answering_time')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.reading_time:
            seconds = self.instance.reading_time
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

    def to_seconds(self, value, unit):
        if not value:
            return 0
        if unit == 'minutes':
            return int(value * 60)
        elif unit == 'hours':
            return int(value * 3600)
        return int(value)

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Convert unit values to seconds before saving
        rt_value = self.cleaned_data.get('reading_time_value') or 0
        rt_unit = self.cleaned_data.get('reading_time_unit') or 'seconds'
        at_value = self.cleaned_data.get('answering_time_value') or 0
        at_unit = self.cleaned_data.get('answering_time_unit') or 'seconds'

        instance.reading_time = self.to_seconds(rt_value, rt_unit)
        instance.answering_time = self.to_seconds(at_value, at_unit)

        if commit:
            instance.save()
        return instance
