# Email setup

KabayaniTrack sends password-reset links and (in future) emergency alerts by
email. This page explains how to make those emails actually arrive.

## Why emails currently do not send

* `smtp.pythonanywhere.com` **does not exist**. PythonAnywhere does not run an
  SMTP server, so the old default could never work.
* `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` were empty, so authentication
  always failed.
* The failure was caught and only written to the server log, so the page still
  said "check your email".

## Production checklist (PythonAnywhere)

1. Create a dedicated Gmail account, e.g. `kabayanitrack.alerts@gmail.com`.
   Do **not** reuse a personal account.
2. Enable **2-Step Verification** on that account.
3. Create an **App Password** (Google Account → Security → App passwords).
   Copy the 16-character password.
4. In the PythonAnywhere **Web** tab, add these environment variables, then
   click **Reload**:

   ```
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=kabayanitrack.alerts@gmail.com
   EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx
   DEFAULT_FROM_EMAIL=kabayanitrack.alerts@gmail.com
   EMAIL_TIMEOUT=10
   ```

5. Verify from a Bash console:

   ```bash
   cd ~/KabayaniTrack
   source .venv/bin/activate
   python manage.py sendtestemail YOUR_REAL_EMAIL@gmail.com
   ```

   No output means it worked. Any traceback shows the exact SMTP error.

6. Test the real flow: open `/password-reset/`, enter a registered address and
   confirm the email arrives (check spam).

## Local development

With `DEBUG=True` the console backend is used, so the message is printed in the
terminal and the reset link is also shown on the page. Nothing is sent.

To test real delivery locally, export the same variables (or set
`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`) before running
`python manage.py runserver`.

## Notes

* PythonAnywhere **free** accounts may only connect to Gmail's SMTP servers.
  Other providers need a paid account, or an HTTPS-based email API.
* Gmail limits a free account to roughly 500 recipients per day. That is fine
  for password resets; use a transactional provider before sending bulk alerts.
