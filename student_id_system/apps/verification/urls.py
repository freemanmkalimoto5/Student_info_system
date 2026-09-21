from django.urls import path

from . import views

app_name = 'verification'

urlpatterns = [
    path('<str:student_number>/', views.verify_student, name='scan'),
]
