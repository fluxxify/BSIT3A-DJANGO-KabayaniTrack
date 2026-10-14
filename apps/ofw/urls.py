from django.urls import path

from . import views

app_name = 'ofw'

urlpatterns = [
    # OFW profiles
    path('profiles/', views.profile_list_page, name='profile_list'),
    path('profiles/ajax/list/', views.profile_list_ajax, name='profile_list_ajax'),
    path('profiles/ajax/get/<int:pk>/', views.profile_get_ajax, name='profile_get_ajax'),
    path('profiles/ajax/save/', views.profile_save_ajax, name='profile_save_ajax'),
    path('profiles/ajax/delete/<int:pk>/', views.profile_delete_ajax, name='profile_delete_ajax'),

    # Welfare assessments
    path('welfare/', views.assessment_list_page, name='assessment_list'),
    path('welfare/ajax/list/', views.assessment_list_ajax, name='assessment_list_ajax'),
    path('welfare/ajax/get/<int:pk>/', views.assessment_get_ajax, name='assessment_get_ajax'),
    path('welfare/ajax/save/', views.assessment_save_ajax, name='assessment_save_ajax'),
    path('welfare/ajax/delete/<int:pk>/', views.assessment_delete_ajax, name='assessment_delete_ajax'),

    # Check-ins
    path('checkins/', views.checkin_list_page, name='checkin_list'),
    path('checkins/ajax/list/', views.checkin_list_ajax, name='checkin_list_ajax'),
    path('checkins/ajax/get/<int:pk>/', views.checkin_get_ajax, name='checkin_get_ajax'),
    path('checkins/ajax/save/', views.checkin_save_ajax, name='checkin_save_ajax'),
    path('checkins/ajax/delete/<int:pk>/', views.checkin_delete_ajax, name='checkin_delete_ajax'),

    # Concerns
    path('concerns/', views.concern_list_page, name='concern_list'),
    path('concerns/ajax/list/', views.concern_list_ajax, name='concern_list_ajax'),
    path('concerns/ajax/get/<int:pk>/', views.concern_get_ajax, name='concern_get_ajax'),
    path('concerns/ajax/save/', views.concern_save_ajax, name='concern_save_ajax'),
    path('concerns/ajax/delete/<int:pk>/', views.concern_delete_ajax, name='concern_delete_ajax'),

    # Support documentation
    path('support/', views.support_list_page, name='support_list'),
    path('support/ajax/list/', views.support_list_ajax, name='support_list_ajax'),
    path('support/ajax/get/<int:pk>/', views.support_get_ajax, name='support_get_ajax'),
    path('support/ajax/save/', views.support_save_ajax, name='support_save_ajax'),
    path('support/ajax/delete/<int:pk>/', views.support_delete_ajax, name='support_delete_ajax'),

    # Monitoring reports
    path('reports/', views.report_list_page, name='report_list'),
    path('reports/ajax/list/', views.report_list_ajax, name='report_list_ajax'),
    path('reports/ajax/get/<int:pk>/', views.report_get_ajax, name='report_get_ajax'),
    path('reports/ajax/save/', views.report_save_ajax, name='report_save_ajax'),
    path('reports/ajax/delete/<int:pk>/', views.report_delete_ajax, name='report_delete_ajax'),
]
