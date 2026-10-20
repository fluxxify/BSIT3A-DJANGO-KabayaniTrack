from django.urls import path
from django.views.generic import RedirectView

from . import portal_views, views

app_name = 'ofw'

urlpatterns = [
    # Legacy URL: "support" was renamed to "contacts"
    path('support/', RedirectView.as_view(pattern_name='ofw:contact_list', permanent=True)),

    # OFW self-service portal
    path('portal/', portal_views.portal_home, name='portal'),
    path('portal/profile/', portal_views.portal_profile, name='portal_profile'),
    path('portal/checkins/', portal_views.portal_checkins, name='portal_checkins'),
    path('portal/concerns/', portal_views.portal_concerns, name='portal_concerns'),
    path('portal/contacts/', portal_views.portal_contacts, name='portal_contacts'),

    # OFW profiles
    path('profiles/', views.profile_list_page, name='profile_list'),
    path('profiles/<int:pk>/', views.profile_detail, name='profile_detail'),
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
    path('checkins/<int:pk>/', views.checkin_detail, name='checkin_detail'),
    path('checkins/ajax/list/', views.checkin_list_ajax, name='checkin_list_ajax'),
    path('checkins/ajax/get/<int:pk>/', views.checkin_get_ajax, name='checkin_get_ajax'),
    path('checkins/ajax/save/', views.checkin_save_ajax, name='checkin_save_ajax'),
    path('checkins/ajax/delete/<int:pk>/', views.checkin_delete_ajax, name='checkin_delete_ajax'),

    # Concerns
    path('concerns/', views.concern_list_page, name='concern_list'),
    path('concerns/<int:pk>/', views.concern_detail, name='concern_detail'),
    path('concerns/ajax/list/', views.concern_list_ajax, name='concern_list_ajax'),
    path('concerns/ajax/get/<int:pk>/', views.concern_get_ajax, name='concern_get_ajax'),
    path('concerns/ajax/save/', views.concern_save_ajax, name='concern_save_ajax'),
    path('concerns/ajax/delete/<int:pk>/', views.concern_delete_ajax, name='concern_delete_ajax'),

    # Emergency contacts
    path('contacts/', views.contact_list_page, name='contact_list'),
    path('contacts/ajax/list/', views.contact_list_ajax, name='contact_list_ajax'),
    path('contacts/ajax/get/<int:pk>/', views.contact_get_ajax, name='contact_get_ajax'),
    path('contacts/ajax/save/', views.contact_save_ajax, name='contact_save_ajax'),
    path('contacts/ajax/delete/<int:pk>/', views.contact_delete_ajax, name='contact_delete_ajax'),

    # Family emergency-contact requests (OFW submits, management reviews)
    path('contact-requests/', views.contact_request_list_page, name='contact_request_list'),
    path('contact-requests/<int:pk>/decide/', views.contact_request_decide, name='contact_request_decide'),

    # Monitoring reports
    path('reports/', views.report_list_page, name='report_list'),
    path('reports/ajax/list/', views.report_list_ajax, name='report_list_ajax'),
    path('reports/ajax/get/<int:pk>/', views.report_get_ajax, name='report_get_ajax'),
    path('reports/ajax/save/', views.report_save_ajax, name='report_save_ajax'),
    path('reports/ajax/delete/<int:pk>/', views.report_delete_ajax, name='report_delete_ajax'),
]
