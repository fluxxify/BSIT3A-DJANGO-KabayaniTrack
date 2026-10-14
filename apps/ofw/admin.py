from django.contrib import admin

from .models import (
    CheckIn,
    Concern,
    MonitoringReport,
    OFWProfile,
    SupportRecord,
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
    list_display = ('ofw', 'checkin_date', 'method', 'condition', 'location')
    list_filter = ('method', 'condition')
    search_fields = ('ofw__first_name', 'ofw__last_name', 'location', 'contacted_person')


@admin.register(Concern)
class ConcernAdmin(admin.ModelAdmin):
    list_display = ('title', 'ofw', 'category', 'severity', 'status', 'reported_date')
    list_filter = ('category', 'severity', 'status')
    search_fields = ('title', 'description', 'ofw__first_name', 'ofw__last_name')


@admin.register(SupportRecord)
class SupportRecordAdmin(admin.ModelAdmin):
    list_display = ('title', 'ofw', 'support_type', 'provider', 'amount', 'status', 'date_provided')
    list_filter = ('support_type', 'status')
    search_fields = ('title', 'provider', 'ofw__first_name', 'ofw__last_name')


@admin.register(MonitoringReport)
class MonitoringReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'report_type', 'period_start', 'period_end', 'country', 'status')
    list_filter = ('report_type', 'status')
    search_fields = ('title', 'country', 'prepared_by')
