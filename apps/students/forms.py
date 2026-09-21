from django import forms

from .models import Student


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        # student_number is deliberately excluded: it's auto-assigned by
        # renumber_students() based on class + alphabetical order, not
        # entered manually. grade_class now renders as a dropdown since
        # the model field has fixed choices (form one..six).
        fields = [
            'first_name', 'middle_name', 'last_name',
            'date_of_birth', 'photo',
            'grade_class', 'status',
            'father_name', 'father_phone', 'father_whatsapp',
            'mother_name', 'mother_phone', 'mother_whatsapp',
            'guardian_name', 'guardian_phone', 'guardian_relationship',
            'parish',
            'full_address', 'region', 'district', 'ward',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'full_address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Bootstrap-style styling hook for every field; safe to remove
        # or replace if you're using a different CSS framework.
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label='CSV File',
        help_text='Upload a .csv file with columns matching the sample template.'
    )

    def clean_csv_file(self):
        file = self.cleaned_data['csv_file']
        if not file.name.lower().endswith('.csv'):
            raise forms.ValidationError('Please upload a .csv file.')
        return file
