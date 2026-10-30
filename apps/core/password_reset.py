from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def password_reset_request(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            for user in form.get_users(email):
                if not user.has_usable_password():
                    continue
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                reset_url = request.build_absolute_uri(f'/reset/{uid}/{token}/')
                return render(request, 'auth/password_reset_done.html', {
                    'reset_url': reset_url,
                    'email': email,
                })
            # Even if no user found, show same page for security
            return render(request, 'auth/password_reset_done.html', {
                'email': email,
            })
    else:
        form = PasswordResetForm()
    return render(request, 'auth/password_reset_form.html', {'form': form})
