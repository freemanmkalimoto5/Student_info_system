from django.urls import path

from . import views

app_name = 'qrcodes'

urlpatterns = [
    path('', views.qr_list, name='list'),
    path('id-cards/', views.id_cards_list, name='id_cards_list'),
    path('regenerate-all/', views.qr_regenerate_all, name='regenerate_all'),
    path('print/', views.qr_print_choose, name='print_choose'),
    path('print/batch/', views.qr_print_batch, name='print_batch'),
    path('download/batch/', views.qr_download_batch_pdf, name='download_batch_pdf'),
    path('id-cards/print/batch/', views.id_cards_print_batch, name='id_cards_print_batch'),
    path('id-cards/download/batch/', views.id_cards_download_batch_pdf, name='id_cards_download_batch_pdf'),
    path('<int:pk>/preview/', views.qr_preview, name='preview'),
    path('<int:pk>/regenerate/', views.qr_regenerate, name='regenerate'),
    path('<int:pk>/print/', views.qr_print, name='print'),
    path('<int:pk>/download/', views.qr_download_pdf, name='download_pdf'),
]
