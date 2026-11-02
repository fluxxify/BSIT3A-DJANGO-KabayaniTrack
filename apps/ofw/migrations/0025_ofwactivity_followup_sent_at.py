from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kabayan', '0024_alter_policereport_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='ofwactivity',
            name='followup_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When the 6-day inactivity follow-up was sent to management.',
                null=True,
            ),
        ),
    ]
