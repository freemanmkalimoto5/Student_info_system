from django.urls import path

from . import views

app_name = 'qrcodes'

urlpatterns = [
    path('', views.qr_list, name='list'),                                    # NEW
    path('regenerate-all/', views.qr_regenerate_all, name='regenerate_all'),  # NEW
    path('<int:pk>/preview/', views.qr_preview, name='preview'),
    path('<int:pk>/regenerate/', views.qr_regenerate, name='regenerate'),
    path('<int:pk>/print/', views.qr_print, name='print'),
    path('<int:pk>/download/', views.qr_download_pdf, name='download_pdf'),
]
