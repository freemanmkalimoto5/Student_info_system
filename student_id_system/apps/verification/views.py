from django.shortcuts import render, get_object_or_404

from apps.students.models import Student


def verify_student(request, student_number):
    """
    Public page shown when someone scans a student's QR code.
    No login required (by design, for now) so anyone with the
    physical card can verify the holder's identity at a glance.

    This will be locked down later (see project notes) by wrapping
    this view with @login_required or adding a token/signature check
    instead of a bare student_number lookup.
    """
    student = get_object_or_404(Student, student_number=student_number)
    return render(request, 'verification/scan_result.html', {'student': student})
