"""ModelForms for the OFW monitoring domain with Bootstrap-friendly widgets."""

import os

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyContact,
    EmergencyContactRequest,
    MonitoringReport,
    OFWProfile,
    WelfareAssessment,
)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A FileField that accepts several files at once (Django docs pattern)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            raise ValidationError('Invalid file upload.', code='invalid')
        return [single_file_clean(item, initial) for item in data]


class StyledModelForm(forms.ModelForm):
    """Base ModelForm that applies Tabler/Bootstrap styling and scopes OFW choices."""

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        if user is not None and 'ofw' in self.fields:
            if user.is_superuser or user.is_staff:
                self.fields['ofw'].queryset = OFWProfile.objects.all()
            else:
                self.fields['ofw'].queryset = OFWProfile.objects.filter(user=user)

        if user is not None and 'concern' in self.fields:
            if user.is_superuser or user.is_staff:
                self.fields['concern'].queryset = Concern.objects.all()
            else:
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
            'first_name', 'last_name', 'passport_number', 'birth_date', 'age', 'sex',
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
        if (ofw is not None and self.user is not None
                and not (self.user.is_superuser or self.user.is_staff)
                and ofw.user_id != self.user.id):
            raise ValidationError('You can only assess OFWs that belong to you.')
        return cleaned


class CheckInForm(StyledModelForm):
    class Meta:
        model = CheckIn
        fields = ['ofw', 'checkin_date', 'method', 'condition', 'notes']

    def clean(self):
        cleaned = super().clean()
        ofw = cleaned.get('ofw')
        if (ofw is not None and self.user is not None
                and not (self.user.is_superuser or self.user.is_staff)
                and ofw.user_id != self.user.id):
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
        if (ofw is not None and self.user is not None
                and not (self.user.is_superuser or self.user.is_staff)
                and ofw.user_id != self.user.id):
            raise ValidationError('You can only report concerns for OFWs that belong to you.')
        return cleaned


class EmergencyContactForm(StyledModelForm):
    # Declared explicitly so forms.URLField gets assume_scheme (models.URLField
    # can't pass it, and Django 5.x warns when the scheme is left implicit).
    website = forms.URLField(
        required=False,
        assume_scheme='https',
        help_text='Official website (leave blank to use the default for this type)',
    )

    class Meta:
        model = EmergencyContact
        fields = [
            'name', 'contact_type', 'country', 'city', 'phone', 'email',
            'website', 'address', 'notes',
        ]


class MonitoringReportForm(StyledModelForm):
    class Meta:
        model = MonitoringReport
        fields = [
            'title', 'report_type', 'period_start', 'period_end', 'country',
            'summary', 'status', 'attachment',
        ]

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('period_start')
        end = cleaned.get('period_end')
        if start and end and end < start:
            raise ValidationError('Period end must not be earlier than period start.')
        return cleaned


class OFWPortalProfileForm(StyledModelForm):
    """Fields an OFW may maintain on their own profile.

    Welfare status and case remarks stay under management control, so they are
    intentionally excluded here.
    """

    class Meta:
        model = OFWProfile
        fields = [
            'first_name', 'last_name', 'passport_number', 'birth_date', 'age', 'sex',
            'contact_number', 'email', 'permanent_address', 'country',
            'city_abroad', 'employer_name', 'occupation', 'agency',
            'deployment_date', 'contract_end_date',
        ]
        widgets = {
            'country': forms.TextInput(attrs={
                'list': 'country-options',
                'autocomplete': 'off',
                'placeholder': 'Select or type your country',
            }),
            'city_abroad': forms.TextInput(attrs={
                'list': 'city-options',
                'autocomplete': 'off',
                'placeholder': 'Select or type your city',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Choices are suggestions only (datalist), so keep the free-text inputs
        # styled consistently with the rest of the form.
        self.fields['city_abroad'].help_text = (
            'City or area in your country of deployment.'
        )


class OFWSelfCheckInForm(StyledModelForm):
    """Self-service check-in: the OFW reports their own condition."""

    class Meta:
        model = CheckIn
        fields = ['method', 'condition', 'notes']


class FamilyContactRequestForm(StyledModelForm):
    """An OFW's request to add a family member as an emergency contact.

    The request is reviewed by the management team before it becomes a real
    emergency contact, so specifying a desired ``contact_type`` is unnecessary.
    """

    class Meta:
        model = EmergencyContactRequest
        fields = ['name', 'relationship', 'phone', 'email', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Full name of your family member'}),
            'relationship': forms.TextInput(attrs={'placeholder': 'e.g. Spouse, Parent, Sibling'}),
            'phone': forms.TextInput(attrs={'placeholder': '+63 917 000 0000'}),
            'address': forms.TextInput(attrs={'placeholder': 'Home address in the Philippines'}),
            'notes': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Anything the team should know (optional)',
            }),
        }
        labels = {
            'name': 'Family Member Name',
            'phone': 'Contact Number',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False


class OFWSelfConcernForm(StyledModelForm):
    """Self-service concern report submitted by an OFW."""

    proof_files = MultipleFileField(
        required=False,
        label='Photo / Video Proof',
        help_text=(
            'Attach photos or videos as proof (e.g. evidence of maltreatment). '
            f'Up to {ConcernProof.MAX_FILES} files, '
            f'{ConcernProof.MAX_FILE_SIZE // (1024 * 1024)} MB each. '
            'Accepted: JPG, PNG, GIF, WEBP, MP4, MOV, WEBM, etc.'
        ),
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
            'accept': ','.join(
                list(ConcernProof.IMAGE_EXTENSIONS) + list(ConcernProof.VIDEO_EXTENSIONS)
            ),
        }),
    )

    class Meta:
        model = Concern
        fields = ['title', 'category', 'severity', 'description']

    def clean_proof_files(self):
        files = self.cleaned_data.get('proof_files') or []
        if len(files) > ConcernProof.MAX_FILES:
            raise ValidationError(
                f'You can attach at most {ConcernProof.MAX_FILES} proof files.'
            )
        allowed = ConcernProof.IMAGE_EXTENSIONS + ConcernProof.VIDEO_EXTENSIONS
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in allowed:
                raise ValidationError(
                    f'"{f.name}" is not an accepted file type. '
                    'Only photos and videos are allowed as proof.'
                )
            if f.size > ConcernProof.MAX_FILE_SIZE:
                raise ValidationError(
                    f'"{f.name}" is larger than '
                    f'{ConcernProof.MAX_FILE_SIZE // (1024 * 1024)} MB.'
                )
        return files
