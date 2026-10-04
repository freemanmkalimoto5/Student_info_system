from django.urls import path

from . import views, bulk_views

app_name = 'students'

urlpatterns = [
    path('', views.student_list, name='list'),
    path('new/', views.student_create, name='create'),
    path('import/', views.student_import, name='import'),
    path('import/export/', bulk_views.student_export, name='export'),      # "Download a file"
    path('import/replace/', bulk_views.student_replace, name='replace'),   # "Replace existing details"
    path('import/<int:job_id>/progress/', views.import_progress, name='import_progress'),
    path('import/<int:job_id>/status/', views.import_status, name='import_status'),
    path('<int:pk>/', views.student_detail, name='detail'),
    path('<int:pk>/edit/', views.student_update, name='update'),
    path('<int:pk>/delete/', views.student_delete, name='delete'),
]
