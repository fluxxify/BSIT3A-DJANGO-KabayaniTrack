"""ModelForms for the OFW monitoring domain with Bootstrap-friendly widgets."""

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    CheckIn,
    Concern,
    MonitoringReport,
    OFWProfile,
    SupportRecord,
    WelfareAssessment,
)


class StyledModelForm(forms.ModelForm):
    """Base ModelForm that applies Tabler/Bootstrap styling and scopes OFW choices."""

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        if user is not None and 'ofw' in self.fields:
            self.fields['ofw'].queryset = OFWProfile.objects.filter(user=user)

        if user is not None and 'concern' in self.fields:
            self.fields['concern'].queryset = Concern.objects.filter(user=user)

        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault('class', 'form-select')
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault('class', 'form-control')
            else:
                widget.attrs.setdefault('class', 'form-control')

            if isinstance(widget, forms.DateTimeInput) and not isinstance(widget, forms.DateInput):
                widget.input_type = 'datetime-local'
            elif isinstance(widget, forms.DateInput):
                widget.input_type = 'date'


class OFWProfileForm(StyledModelForm):
    class Meta:
        model = OFWProfile
        fields = [
            'first_name', 'last_name', 'passport_number', 'birth_date', 'sex',
            'contact_number', 'email', 'permanent_address', 'country',
            'city_abroad', 'employer_name', 'occupation', 'agency',
            'deployment_date', 'contract_end_date', 'welfare_status', 'remarks',
        ]


class WelfareAssessmentForm(StyledModelForm):
    class Meta:
        model = WelfareAssessment
        fields = ['ofw', 'status', 'risk_level', 'assessment_date', 'assessor', 'notes']

    def clean(self):
        cleaned = super().clean()
        ofw = cleaned.get('ofw')
        if ofw is not None and self.user is not None and ofw.user_id != self.user.id:
            raise ValidationError('You can only assess OFWs that belong to you.')
        return cleaned


class CheckInForm(StyledModelForm):
    class Meta:
        model = CheckIn
        fields = ['ofw', 'checkin_date', 'method', 'condition', 'location', 'contacted_person', 'notes']

    def clean(self):
        cleaned = super().clean()
        ofw = cleaned.get('ofw')
        if ofw is not None and self.user is not None and ofw.user_id != self.user.id:
            raise ValidationError('You can only log check-ins for OFWs that belong to you.')
        return cleaned


class ConcernForm(StyledModelForm):
    class Meta:
        model = Concern
        fields = [
            'ofw', 'title', 'category', 'severity', 'status',
            'reported_date', 'description', 'actions_taken', 'resolved_date',
        ]

    def clean(self):
        cleaned = super().clean()
        ofw = cleaned.get('ofw')
        if ofw is not None and self.user is not None and ofw.user_id != self.user.id:
            raise ValidationError('You can only report concerns for OFWs that belong to you.')
        return cleaned


class SupportRecordForm(StyledModelForm):
    class Meta:
        model = SupportRecord
        fields = [
            'ofw', 'concern', 'support_type', 'title', 'description', 'provider',
            'amount', 'date_provided', 'status', 'document',
        ]

    def clean(self):
        cleaned = super().clean()
        ofw = cleaned.get('ofw')
        concern = cleaned.get('concern')
        if ofw is not None and self.user is not None and ofw.user_id != self.user.id:
            raise ValidationError('You can only document support for OFWs that belong to you.')
        if concern is not None and ofw is not None and concern.ofw_id != ofw.id:
            raise ValidationError('The selected concern does not belong to the selected OFW.')
        return cleaned


class MonitoringReportForm(StyledModelForm):
    class Meta:
        model = MonitoringReport
        fields = [
            'title', 'report_type', 'period_start', 'period_end', 'country',
            'total_ofws', 'total_concerns', 'total_support_cases', 'summary',
            'findings', 'recommendations', 'prepared_by', 'status', 'attachment',
        ]

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('period_start')
        end = cleaned.get('period_end')
        if start and end and end < start:
            raise ValidationError('Period end must not be earlier than period start.')
        return cleaned
