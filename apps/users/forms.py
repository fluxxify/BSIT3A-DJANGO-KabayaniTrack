from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .models import Agency


class AgencyForm(forms.ModelForm):
    """Create or edit a partner agency without touching existing records."""

    class Meta:
        model = Agency
        fields = [
            'name',
            'slug',
            'website',
            'category',
            'address',
            'phone',
            'email',
            'description',
            'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault('class', 'form-select')
            else:
                widget.attrs.setdefault('class', 'form-control')

    def clean_name(self):
        name = ' '.join((self.cleaned_data.get('name') or '').split())
        if not name:
            raise ValidationError('Agency name is required.')
        duplicates = Agency.objects.filter(name__iexact=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError('An agency with this name already exists.')
        return name

    def clean_slug(self):
        slug = (self.cleaned_data.get('slug') or '').strip().lower()
        if not slug:
            slug = slugify(self.cleaned_data.get('name') or '')
        if not slug:
            raise ValidationError(
                'Enter a short URL name, or use a name that can be converted '
                'into one.'
            )
        duplicates = Agency.objects.filter(slug__iexact=slug)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError('An agency with this URL name already exists.')
        return slug


class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'password',
            'is_staff',
            'is_active'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Force all fields required except password
        for field in self.fields:
            if field != 'password':
                self.fields[field].required = True

        # Password required only when creating
        if not self.instance.pk:
            self.fields['password'].required = True

    def save(self, commit=True):
        user = super().save(commit=False)

        password = self.cleaned_data.get('password')

        # Only change password if user entered one
        if password:
            user.set_password(password)

        if commit:
            user.save()

        return user