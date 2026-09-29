from django.shortcuts import render, get_object_or_404

from apps.students.models import Student


def verify_student(request, student_number):
    """
    Public page shown when someone opens a student's verification link.
    An expired card shows NOTHING about the student. Graduated students'
    cards never expire.
    """
    student = get_object_or_404(Student, student_number=student_number)

    card = getattr(student, 'id_card', None)     # None if no card exists yet
    if card is not None and card.is_expired:
        return render(request, 'verification/expired.html')

    return render(request, 'verification/scan_result.html', {'student': student})
