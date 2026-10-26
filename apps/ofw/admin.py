from django.contrib import admin

from .models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyContact,
    MonitoringReport,
    Notification,
    OFWProfile,
    WelfareAssessment,
)


@admin.register(OFWProfile)
class OFWProfileAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'country', 'employer_name', 'welfare_status')
    list_filter = ('welfare_status', 'country', 'sex')
    search_fields = ('first_name', 'last_name', 'passport_number', 'country', 'employer_name')


@admin.register(WelfareAssessment)
class WelfareAssessmentAdmin(admin.ModelAdmin):
    list_display = ('ofw', 'status', 'risk_level', 'assessment_date', 'assessor')
    list_filter = ('status', 'risk_level')
    search_fields = ('ofw__first_name', 'ofw__last_name', 'assessor')


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ('ofw', 'checkin_date', 'method', 'condition')
    list_filter = ('method', 'condition')
    search_fields = ('ofw__first_name', 'ofw__last_name', 'notes')


class ConcernProofInline(admin.TabularInline):
    model = ConcernProof
    extra = 0
    readonly_fields = ('uploaded_at',)


@admin.register(Concern)
class ConcernAdmin(admin.ModelAdmin):
    list_display = ('title', 'ofw', 'category', 'severity', 'status', 'reported_date')
    list_filter = ('category', 'severity', 'status')
    search_fields = ('title', 'description', 'ofw__first_name', 'ofw__last_name')
    inlines = [ConcernProofInline]


@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_type', 'country', 'city', 'phone', 'email', 'website')
    list_filter = ('contact_type', 'country')
    search_fields = ('name', 'country', 'city', 'phone', 'email', 'website')


@admin.register(MonitoringReport)
class MonitoringReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'report_type', 'period_start', 'period_end', 'country', 'status')
    list_filter = ('report_type', 'status')
    search_fields = ('title', 'country', 'summary')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'level', 'is_read', 'created_at')
    list_filter = ('level', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username')
    readonly_fields = ('created_at',)
