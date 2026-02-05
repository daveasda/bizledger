# Add Contra voucher type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0003_add_ledger_details_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='voucher',
            name='voucher_type',
            field=models.CharField(
                choices=[
                    ('RECEIPT', 'Receipt'),
                    ('PAYMENT', 'Payment'),
                    ('JOURNAL', 'Journal'),
                    ('CONTRA', 'Contra'),
                ],
                max_length=16,
            ),
        ),
    ]
