from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Page
    path('', views.user_list_page, name='user_list'),

    # Agencies (administrator only)
    path('agencies/', views.agency_list_page, name='agency_list'),
    path('agencies/<int:pk>/', views.agency_detail, name='agency_detail'),
    path('agencies/ajax/get/<int:pk>/', views.agency_get_ajax, name='agency_get_ajax'),
    path('agencies/ajax/save/', views.agency_save_ajax, name='agency_save_ajax'),
    path('agencies/ajax/toggle/<int:pk>/', views.agency_toggle_ajax, name='agency_toggle_ajax'),

    # AJAX
    path('ajax/list/', views.user_list_ajax, name='user_list_ajax'),
    path('ajax/get/<int:pk>/', views.user_get_ajax, name='user_get_ajax'),
    path('ajax/save/', views.user_save_ajax, name='user_save_ajax'),
    path('ajax/delete/<int:pk>/', views.user_delete_ajax, name='user_delete_ajax'),
]