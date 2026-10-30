import logging

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def _shows_link_instead_of_email():
    """Return True when email cannot actually be delivered.

    The console and file backends only write the message locally (they are the
    defaults for local development), so the reset link is shown on the page
    instead. Any SMTP-based backend sends a real email.
    """
    backend = settings.EMAIL_BACKEND or ''
    return backend.endswith(
        ('console.EmailBackend', 'filebased.EmailBackend')
    )


def _build_reset_url(request, user):
    return request.build_absolute_uri(reverse('password_reset_confirm', kwargs={
        'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': default_token_generator.make_token(user),
    }))


def password_reset_request(request):
    if request.method != 'POST':
        return render(request, 'auth/password_reset_form.html', {
            'form': PasswordResetForm(),
        })

    form = PasswordResetForm(request.POST)
    if not form.is_valid():
        return render(request, 'auth/password_reset_form.html', {'form': form})

    email = form.cleaned_data['email']
    users = list(form.get_users(email))
    context = {'email': email}

    if users and _shows_link_instead_of_email():
        # No deliverable mail backend (local development): surface the link so
        # the password can still be reset.
        context['reset_url'] = _build_reset_url(request, users[0])
    elif users:
        try:
            form.save(
                request=request,
                from_email=settings.DEFAULT_FROM_EMAIL,
                email_template_name='auth/password_reset_email.html',
                subject_template_name='auth/password_reset_subject.txt',
            )
        except Exception:
            # Do not reveal whether the address belongs to an account, but make
            # the failure visible in the server logs.
            logger.exception(
                'Could not send password reset email to %s', email
            )

    # Always render the same confirmation, whether or not the address matched an
    # account, to avoid leaking which emails are registered.
    return render(request, 'auth/password_reset_done.html', context)
