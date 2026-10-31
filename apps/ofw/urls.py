from django.urls import path
from django.views.generic import RedirectView

from . import notification_views, portal_views, views

app_name = 'ofw'

urlpatterns = [
    # Legacy URL: "support" was renamed to "contacts"
    path('support/', RedirectView.as_view(pattern_name='ofw:contact_list', permanent=True)),

    # OFW self-service portal
    path('portal/', portal_views.portal_home, name='portal'),
    path('portal/profile/', portal_views.portal_profile, name='portal_profile'),
    path('portal/cities/', portal_views.portal_cities, name='portal_cities'),
    path('portal/checkins/', portal_views.portal_checkins, name='portal_checkins'),
    path('portal/concerns/', portal_views.portal_concerns, name='portal_concerns'),
    path('portal/contacts/', portal_views.portal_contacts, name='portal_contacts'),
    path('portal/sos/', portal_views.portal_sos, name='portal_sos'),
    path('portal/contacts/<int:pk>/edit/', portal_views.portal_contact_edit, name='portal_contact_edit'),
    path('portal/contacts/<int:pk>/delete/', portal_views.portal_contact_delete, name='portal_contact_delete'),

    # In-app notifications (shared by OFW accounts and management users)
    path('notifications/', notification_views.notifications_page, name='notifications'),
    path('notifications/read-all/', notification_views.notifications_mark_all_read, name='notifications_mark_all_read'),
    path('notifications/delete-all/', notification_views.notifications_delete_all, name='notifications_delete_all'),
    path('notifications/<int:pk>/', notification_views.notification_open, name='notification_open'),
    path('notifications/<int:pk>/read/', notification_views.notification_mark_read, name='notification_mark_read'),
    path('notifications/<int:pk>/delete/', notification_views.notification_delete, name='notification_delete'),

    # OFW profiles
    path('profiles/', views.profile_list_page, name='profile_list'),
    path('profiles/<int:pk>/', views.profile_detail, name='profile_detail'),
    path('profiles/ajax/list/', views.profile_list_ajax, name='profile_list_ajax'),
    path('profiles/ajax/get/<int:pk>/', views.profile_get_ajax, name='profile_get_ajax'),
    path('profiles/ajax/save/', views.profile_save_ajax, name='profile_save_ajax'),
    path('profiles/ajax/delete/<int:pk>/', views.profile_delete_ajax, name='profile_delete_ajax'),
    path('profiles/ajax/delete-all/', views.profile_delete_all_ajax, name='profile_delete_all_ajax'),

    # Welfare assessments
    path('welfare/', views.assessment_list_page, name='assessment_list'),
    path('welfare/ajax/list/', views.assessment_list_ajax, name='assessment_list_ajax'),
    path('welfare/ajax/get/<int:pk>/', views.assessment_get_ajax, name='assessment_get_ajax'),
    path('welfare/ajax/save/', views.assessment_save_ajax, name='assessment_save_ajax'),
    path('welfare/ajax/delete/<int:pk>/', views.assessment_delete_ajax, name='assessment_delete_ajax'),
    path('welfare/ajax/delete-all/', views.assessment_delete_all_ajax, name='assessment_delete_all_ajax'),

    # Check-ins
    path('checkins/', views.checkin_list_page, name='checkin_list'),
    path('checkins/<int:pk>/', views.checkin_detail, name='checkin_detail'),
    path('checkins/ajax/list/', views.checkin_list_ajax, name='checkin_list_ajax'),
    path('checkins/ajax/get/<int:pk>/', views.checkin_get_ajax, name='checkin_get_ajax'),
    path('checkins/ajax/save/', views.checkin_save_ajax, name='checkin_save_ajax'),
    path('checkins/ajax/delete/<int:pk>/', views.checkin_delete_ajax, name='checkin_delete_ajax'),
    path('checkins/ajax/delete-all/', views.checkin_delete_all_ajax, name='checkin_delete_all_ajax'),

    # Concerns
    path('concerns/', views.concern_list_page, name='concern_list'),
    path('concerns/<int:pk>/', views.concern_detail, name='concern_detail'),
    path('concerns/ajax/list/', views.concern_list_ajax, name='concern_list_ajax'),
    path('concerns/ajax/get/<int:pk>/', views.concern_get_ajax, name='concern_get_ajax'),
    path('concerns/ajax/save/', views.concern_save_ajax, name='concern_save_ajax'),
    path('concerns/ajax/delete/<int:pk>/', views.concern_delete_ajax, name='concern_delete_ajax'),
    path('concerns/ajax/delete-all/', views.concern_delete_all_ajax, name='concern_delete_all_ajax'),
    path('concerns/proofs/<int:pk>/delete/', views.concern_proof_delete, name='concern_proof_delete'),

    # Emergency contacts
    path('contacts/', views.contact_list_page, name='contact_list'),
    path('contacts/ajax/list/', views.contact_list_ajax, name='contact_list_ajax'),
    path('contacts/ajax/get/<int:pk>/', views.contact_get_ajax, name='contact_get_ajax'),
    path('contacts/ajax/save/', views.contact_save_ajax, name='contact_save_ajax'),
    path('contacts/ajax/delete/<int:pk>/', views.contact_delete_ajax, name='contact_delete_ajax'),
    path('contacts/ajax/delete-all/', views.contact_delete_all_ajax, name='contact_delete_all_ajax'),

    # Monitoring reports
    path('reports/', views.report_list_page, name='report_list'),
    path('reports/ajax/list/', views.report_list_ajax, name='report_list_ajax'),
    path('reports/ajax/get/<int:pk>/', views.report_get_ajax, name='report_get_ajax'),
    path('reports/ajax/save/', views.report_save_ajax, name='report_save_ajax'),
    path('reports/ajax/delete/<int:pk>/', views.report_delete_ajax, name='report_delete_ajax'),
    path('reports/ajax/delete-all/', views.report_delete_all_ajax, name='report_delete_all_ajax'),

    # --- Emergency warning & location tracker ---

    # Inactive OFW accounts (admin/agency warning dashboard)
    path('inactive-ofws/', views.inactive_ofws_page, name='inactive_ofws'),

    # Emergency alerts
    path('emergency-alerts/', views.emergency_alerts_page, name='emergency_alerts'),
    path('emergency-alerts/<int:pk>/acknowledge/', views.acknowledge_alert, name='acknowledge_alert'),
    path('emergency-alerts/<int:pk>/escalate/', views.escalate_to_police, name='escalate_to_police'),

    # Police reports
    path('police-reports/', views.police_reports_page, name='police_reports'),
    path('police-reports/<int:pk>/submit/', views.police_report_submit, name='police_report_submit'),

    # Safe locations
    path('safe-locations/', views.safe_locations_page, name='safe_locations'),
    path('safe-locations/save/', views.safe_location_save, name='safe_location_save'),
    path('safe-locations/<int:pk>/delete/', views.safe_location_delete, name='safe_location_delete'),

    # Location tracker
    path('location-tracker/', views.location_tracker_page, name='location_tracker'),
    path('location-tracker/ping/', views.location_tracker_ping, name='location_tracker_ping'),
    path('location-context/', views.location_context, name='location_context'),

    # OFW emergency SOS (portal)
    path('portal/emergency-sos/', views.ofw_emergency_sos, name='portal_emergency_sos'),
]
