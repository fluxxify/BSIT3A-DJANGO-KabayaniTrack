# Permanent deployment on PythonAnywhere

This deploys KabayaniTrack to a permanent `https://USERNAME.pythonanywhere.com`
URL. Your PC can be turned off; the site runs on PythonAnywhere's servers.
SQLite and uploaded media live in the project folder, so they survive redeploys.

> The free PythonAnywhere plan is enough for testing/demo. Free accounts have
> CPU limits, no custom domain, and must be logged into periodically. A paid
> plan removes those limits. Do not use the free plan for sensitive real data.

## 1. Create an account

1. Sign up at <https://www.pythonanywhere.com/registration/register/beginner/>.
2. Verify your email and log in.
3. Open **Consoles > Bash**.

## 2. Run the setup script

In the Bash console:

```bash
git clone https://github.com/fluxxify/BSIT3A-DJANGO-KabayaniTrack.git ~/KabayaniTrack
cd ~/KabayaniTrack
PA_USERNAME=YOUR_USERNAME bash deploy/pythonanywhere_setup.sh
```

Replace `YOUR_USERNAME` with your PythonAnywhere username. If you omit
`PA_USERNAME`, the script uses your logged-in Linux username, which is usually
the same. The script:

- creates `.venv` and installs `requirements.txt`;
- runs migrations;
- collects static files for WhiteNoise;
- generates a secret key and `deploy/pythonanywhere_wsgi.generated.py`.

If `python3.10` is unavailable, rerun with an available version, e.g.
`PYTHON_BIN=python3.12`.

## 3. Create the web app

On the **Web** tab:

1. **Add a new web app**.
2. Choose **Manual configuration**, then the same Python version printed by
   the script (normally **Python 3.10**).
3. Set **Source code** to `/home/YOUR_USERNAME/KabayaniTrack`.
4. Set **Working directory** to `/home/YOUR_USERNAME/KabayaniTrack`.
5. Set **Virtualenv** to `/home/YOUR_USERNAME/KabayaniTrack/.venv`.

## 4. Point the WSGI file at Django

On the **Web** tab, click the **WSGI configuration file** link. Delete its
contents and paste the output of:

```bash
cat ~/KabayaniTrack/deploy/pythonanywhere_wsgi.generated.py
```

The generated file already contains your domain, CSRF origin, and a random
secret key. Save it, then click **Reload**.

Open:

```text
https://YOUR_USERNAME.pythonanywhere.com/
```

## 5. Create a login and sample data

In the Bash console:

```bash
cd ~/KabayaniTrack
source .venv/bin/activate
python manage.py createsuperuser
```

Optional sample OFW records (use the superuser you just created):

```bash
python manage.py seed_ofw --user YOUR_ADMIN_USERNAME
```

You can also log in at `/admin/` to create users and OFW profiles.

## Troubleshooting

| Problem | Fix |
|---|---|
| `400 Bad Request` | Check `DJANGO_ALLOWED_HOSTS` in the WSGI file; it must be exactly `YOUR_USERNAME.pythonanywhere.com`. |
| `403 CSRF verification failed` | Check `DJANGO_CSRF_TRUSTED_ORIGINS`; it must be `https://YOUR_USERNAME.pythonanywhere.com`. |
| Static files missing | Run `python manage.py collectstatic --noinput` and reload. |
| `ModuleNotFoundError` | Set the web app's virtualenv to `/home/YOUR_USERNAME/KabayaniTrack/.venv` and reload. |
| Login does not stick on HTTP | Use the `https://` URL; secure cookies are enabled when `DEBUG=False`. |
| Media uploads disappear | On PythonAnywhere media is stored in `/home/YOUR_USERNAME/KabayaniTrack/media`; do not delete that folder. |

## Updating the site later

```bash
cd ~/KabayaniTrack
git pull
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Then click **Reload** on the Web tab.

## Notes

- `DEBUG=False` is set by the generated WSGI file.
- `SECRET_KEY` is generated locally; never commit it.
- Static files are served by WhiteNoise. Media is served by the project's
  range-aware media view, so uploaded videos can play on mobile.
- For a custom domain, HTTPS certificate, and no free-account limits, use a
  paid PythonAnywhere plan or a PaaS such as Render/Railway with PostgreSQL.
