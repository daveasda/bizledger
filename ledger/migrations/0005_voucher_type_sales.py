# Add Sales voucher type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0004_voucher_type_contra'),
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
                    ('SALES', 'Sales'),
                ],
                max_length=16,
            ),
        ),
    ]
