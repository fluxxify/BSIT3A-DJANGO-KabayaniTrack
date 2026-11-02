from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kabayan', '0025_ofwactivity_followup_sent_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='OFWLocationSharing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=False)),
                ('enabled_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ofw', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='location_sharing', to='kabayan.ofwprofile')),
            ],
            options={
                'db_table': 'tblofwlocationsharing',
            },
        ),
    ]
