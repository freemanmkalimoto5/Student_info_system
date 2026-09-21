from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('settings/', views.settings_view, name='settings'),
    path('add-admin/', views.add_admin, name='add_admin'),
    path('complete-profile/', views.complete_profile, name='complete_profile'),
    path('audit-log/', views.audit_log, name='audit_log'),
]
