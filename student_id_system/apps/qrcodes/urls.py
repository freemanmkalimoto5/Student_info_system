from django.urls import path

from . import views

app_name = 'qrcodes'

urlpatterns = [
    path('<int:pk>/preview/', views.qr_preview, name='preview'),
    path('<int:pk>/regenerate/', views.qr_regenerate, name='regenerate'),
    path('<int:pk>/print/', views.qr_print, name='print'),
    path('<int:pk>/download/', views.qr_download_pdf, name='download_pdf'),
]
