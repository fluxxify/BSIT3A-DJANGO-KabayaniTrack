# Email Setup for KabayaniTrack

KabayaniTrack sends email for password resets, inactivity warnings, and
administrator notifications. Local development uses the console backend
(messages are printed to the terminal). Production on PythonAnywhere must use
SMTP — Gmail is the only outbound SMTP host allowed on the free tier.

## 1. Get a Gmail App Password

1. Go to https://myaccount.google.com/apppasswords
2. Sign in with your Gmail account.
3. Select app "Mail" and device "Other (custom name)" → enter "KabayaniTrack".
4. Copy the 16-character app password.

> Use an **App Password**, not your regular Gmail password. App Passwords
> require 2-Step Verification to be enabled on the Google account.

## 2. Set environment variables

Copy `.env.example` to `.env` (production) or edit the local `.env`:

```bash
cp .env.example .env
```

Fill in:

| Variable | Example |
|----------|---------|
| `EMAIL_HOST_USER` | `yourname@gmail.com` |
| `EMAIL_HOST_PASSWORD` | `abcd efgh ijkl mnop` (16 chars, no spaces) |
| `DEFAULT_FROM_EMAIL` | `yourname@gmail.com` |
| `EMAIL_HOST` | `smtp.gmail.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_TIMEOUT` | `10` |

On PythonAnywhere, add these to the web app's **Environment variables** section
in the Web tab, not in a `.env` file (PythonAnywhere does not load `.env`).

## 3. Backend selection

`mysite/settings.py` chooses the backend automatically:

- `DEBUG=True` → `django.core.mail.backends.console.EmailBackend`
  (prints messages to the console; reset links are shown on the page)
- `DEBUG=False` → `django.core.mail.backends.smtp.EmailBackend`
  (sends real email via Gmail SMTP)

> Gmail rejects messages whose `From:` address is not the authenticated
> account, so `DEFAULT_FROM_EMAIL` must match `EMAIL_HOST_USER`.

## 4. Test email

```bash
# Local development (console backend prints the message)
python manage.py shell -c "from django.core.mail import send_mail; send_mail('Test', 'Hello', 'from@example.com', ['to@example.com'], fail_silently=False)"

# Production (real email)
# Trigger a password reset from the login page and check your inbox.
```

## 5. Troubleshooting

| Problem | Fix |
|---------|-----|
| `AuthenticationFailed` | Use a Gmail App Password, not your account password. Enable 2-Step Verification first. |
| `SMTPSocketError` / timeout | PythonAnywhere free tier only allows outbound SMTP to Gmail. Confirm `EMAIL_HOST=smtp.gmail.com` and `EMAIL_PORT=587`. |
| Reset link not received | Check spam folder. Confirm `DEFAULT_FROM_EMAIL` matches `EMAIL_HOST_USER`. |
| Link shown on page instead of emailed | You're on `DEBUG=True` with the console backend. Set `DJANGO_DEBUG=False` and configure SMTP. |

## 6. Rate limits

Gmail free accounts are limited to ~500 emails/day. KabayaniTrack sends
password resets and inactivity warnings only, so this is sufficient for a
small deployment. For higher volume, use a transactional email service
(SendGrid, Mailgun, Amazon SES) and update `EMAIL_BACKEND` accordingly.
