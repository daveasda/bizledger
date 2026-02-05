# Generated migration for adding ledger detail fields
# Adds inventory, opening balance, and mailing fields to Account model

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0002_tally_style_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='inventory_values_affected',
            field=models.BooleanField(blank=True, default=False),
        ),
        migrations.AddField(
            model_name='account',
            name='opening_balance',
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal('0.00'), max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='account',
            name='opening_balance_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='account',
            name='mailing_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='account',
            name='mailing_address',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='account',
            name='mailing_state',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='account',
            name='mailing_pin_code',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='account',
            name='income_tax_no',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='account',
            name='sales_tax_no',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
    ]
