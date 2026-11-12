from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kabayan', '0035_add_emergency_contact_agency'),
    ]

    operations = [
        migrations.AddField(
            model_name='ofwactivity',
            name='offline_notice_until',
            field=models.DateField(
                blank=True,
                help_text='The OFW expects to be offline until this date.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='ofwactivity',
            name='offline_notice_note',
            field=models.CharField(
                blank=True,
                help_text='Short reason shown to agency staff (for example, "at sea").',
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name='ofwactivity',
            name='offline_notice_set_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='ofwactivity',
            name='last_activity_at',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text='Most recent portal use, profile update, or check-in.',
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='ofwactivity',
            name='followup_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When the inactivity follow-up was last sent to management.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='policereport',
            name='report_number',
            field=models.CharField(
                blank=True,
                help_text='Blotter or case number given by the police.',
                max_length=60,
            ),
        ),
        migrations.AddField(
            model_name='policereport',
            name='officer_name',
            field=models.CharField(
                blank=True,
                help_text='Officer handling the report, when known.',
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name='policereport',
            name='follow_up_on',
            field=models.DateField(
                blank=True,
                help_text='Next date the agency should follow up with the police.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='policereport',
            name='resolution_note',
            field=models.TextField(
                blank=True,
                help_text='Outcome recorded when the report is closed.',
            ),
        ),
        migrations.AddField(
            model_name='policereport',
            name='requested_by_ofw',
            field=models.BooleanField(
                default=False,
                help_text='True when the OFW asked for police help from the portal.',
            ),
        ),
    ]
