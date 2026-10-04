from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list, name='list'),
    path('<int:pk>/fix/', views.mark_fixed, name='mark_fixed'),
    path('mark-all-fixed/', views.mark_all_fixed, name='mark_all_fixed'),
    path('clear-fixed/', views.clear_fixed, name='clear_fixed'),
    path('run-checks/', views.run_checks, name='run_checks'),
]
