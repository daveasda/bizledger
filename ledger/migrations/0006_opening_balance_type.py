# Migration for opening_balance_type (Dr/Cr) on Account

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0005_voucher_type_sales'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='opening_balance_type',
            field=models.CharField(
                blank=True,
                choices=[('DR', 'Dr'), ('CR', 'Cr')],
                default='DR',
                max_length=2,
            ),
        ),
    ]
