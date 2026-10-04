from django.shortcuts import render, get_object_or_404

from apps.accounts.models import SiteSettings
from apps.students.models import Student


def verify_student(request, student_number):
    """
    Public page shown when someone scans a student's QR code (no login
    required, by design -- this is meant to work for a security guard,
    a parent, or anyone who finds a lost card). An expired card shows
    nothing about the student. Graduated students' cards never expire.
    """
    student = get_object_or_404(Student, student_number=student_number)

    card = getattr(student, 'id_card', None)
    if card is not None and card.is_expired:
        return render(request, 'verification/expired.html', {
            'site_settings': SiteSettings.load(),
        })

    return render(request, 'verification/scan_result.html', {
        'student': student,
        'site_settings': SiteSettings.load(),
    })
