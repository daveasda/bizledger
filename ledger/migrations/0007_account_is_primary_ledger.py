# Add is_primary_ledger for Profit & Loss A/c (primary ledger with no group)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0006_opening_balance_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='is_primary_ledger',
            field=models.BooleanField(blank=True, default=False),
        ),
    ]
