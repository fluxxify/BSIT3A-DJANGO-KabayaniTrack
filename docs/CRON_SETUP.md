# Scheduled Task: OFW Inactivity Check

KabayaniTrack detects OFW accounts that have not logged in or used the portal
for 3+ days and sends management warnings at day 3 (warning) and day 6
(follow-up). The detection logic lives in the management command:

    python manage.py check_ofw_inactivity

This command must run on a schedule (at least once daily) so inactive accounts
are caught and managers are notified.

## PythonAnywhere (live site)

1. Log in to PythonAnywhere and go to the **Tasks** tab.
2. Click **Add a new task**.
3. Choose **Daily** (or a specific time, e.g. 08:00 Manila time).
4. Enter the command:

   ```bash
   cd /home/YOUR_USERNAME/KabayaniTrack && source .venv/bin/activate && python manage.py check_ofw_inactivity
   ```

5. Save the task.

The command prints a summary line (e.g. `Checked N linked OFW accounts; M currently inactive.`)
which PythonAnywhere captures as task output.

## Local development

Run manually when testing:

    python manage.py check_ofw_inactivity

Or add to your system crontab (Linux/macOS):

    0 8 * * * cd /path/to/KabayaniTrack && .venv/bin/python manage.py check_ofw_inactivity

## What the command does

- Refreshes the activity clock for every linked OFW account (last login,
  last portal activity, days inactive).
- Sends one 3-day warning notification per inactive cycle.
- Sends one 6-day follow-up notification (escalation due).
- Sends an in-app + email reminder to the OFW at day 3.
- Writes audit-log entries for each stage.

It is idempotent: safe to run multiple times per day; notifications are sent
only once per inactivity cycle.
