from datetime import date

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render

from apps.accounts.decorators import admin_required

from .forms import CSVImportForm
from .import_utils import read_uploaded_table_as_csv_text
from .sync_utils import export_students_xlsx, replace_from_table

XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@admin_required
def student_export(request):
    """'Download a file' -- every student in one Excel file."""
    try:
        data = export_students_xlsx()
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('students:import')

    response = HttpResponse(data, content_type=XLSX_TYPE)
    response['Content-Disposition'] = f'attachment; filename="students_{date.today():%Y-%m-%d}.xlsx"'
    return response


@admin_required
def student_replace(request):
    """
    'Replace existing details' -- upload an edited copy of the exported file.
    Changed students are edited, identical ones are skipped, new ones are added.
    """
    if request.method != 'POST':
        return redirect('students:import')

    form = CSVImportForm(request.POST, request.FILES)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect('students:import')

    uploaded = form.cleaned_data['csv_file']
    try:
        csv_text = read_uploaded_table_as_csv_text(uploaded, uploaded.name)
        result = replace_from_table(csv_text, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('students:import')

    return render(request, 'students/student_replace_result.html', {'result': result})
