from django.urls import path
from . import views

app_name = 'pocketmoney'

urlpatterns = [
    path('<int:student_pk>/', views.detail, name='detail'),
    path('<int:student_pk>/add/', views.add, name='add'),
    path('<int:student_pk>/delete/<int:transaction_pk>/', views.delete, name='delete'),
]
