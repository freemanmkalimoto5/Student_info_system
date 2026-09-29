from django.urls import path

from . import views

app_name = 'lostitems'

urlpatterns = [
    path('student/<int:student_pk>/add/', views.add, name='add'),
    path('student/<int:student_pk>/report/', views.report, name='report'),
    path('student/<int:student_pk>/report/pdf/', views.report_pdf, name='report_pdf'),
    path('student/<int:student_pk>/report/send/', views.report_send, name='report_send'),
    path('<int:pk>/pay/', views.pay, name='pay'),
    path('<int:pk>/edit/', views.edit, name='edit'),
    path('<int:pk>/delete/', views.delete, name='delete'),
]
