from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('home/', views.home, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),

    # One clean public entry point per agency.  The registration URL on these
    # pages automatically assigns the new OFW to the agency.
    path('a/<slug:agency_slug>/', views.agency_landing, name='agency_landing'),
    path('a/<slug:agency_slug>/login/', views.login_view, name='agency_login'),
    path('a/<slug:agency_slug>/register/', views.register_view, name='agency_register'),
]