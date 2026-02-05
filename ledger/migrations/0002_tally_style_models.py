# Generated migration for Tally-style ledger models
# Replaces JournalEntry/JournalLine with Voucher/VoucherLine
# Removes EQUITY from root types
# Adds parent-child hierarchy and group/ledger distinction

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0001_initial'),
        ('org', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Remove old JournalEntry and JournalLine
        migrations.DeleteModel(
            name='JournalLine',
        ),
        migrations.DeleteModel(
            name='JournalEntry',
        ),
        
        # Remove unique_together constraint FIRST (before removing code field)
        migrations.AlterUniqueTogether(
            name='account',
            unique_together=set(),
        ),
        
        # Modify Account model - remove old fields
        migrations.RemoveField(
            model_name='account',
            name='code',
        ),
        migrations.RemoveField(
            model_name='account',
            name='type',
        ),
        
        # Modify Account model - add new fields
        migrations.AddField(
            model_name='account',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='ledger.account'),
        ),
        migrations.AddField(
            model_name='account',
            name='is_group',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='account',
            name='root_type',
            field=models.CharField(choices=[('ASSET', 'Asset'), ('LIABILITY', 'Liability'), ('INCOME', 'Income'), ('EXPENSE', 'Expense')], default='ASSET', max_length=16),
        ),
        migrations.AddField(
            model_name='account',
            name='report_type',
            field=models.CharField(choices=[('BS', 'Balance Sheet'), ('PL', 'Profit & Loss')], default='BS', editable=False, max_length=2),
        ),
        migrations.AddField(
            model_name='account',
            name='account_type',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='account',
            name='is_root',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name='account',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        
        # Modify Account name field length
        migrations.AlterField(
            model_name='account',
            name='name',
            field=models.CharField(max_length=255),
        ),
        
        # Add new constraint
        migrations.AddConstraint(
            model_name='account',
            constraint=models.UniqueConstraint(fields=['business', 'name'], name='uniq_account_name_per_business'),
        ),
        
        # Create Voucher model
        migrations.CreateModel(
            name='Voucher',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(max_length=32)),
                ('voucher_type', models.CharField(choices=[('RECEIPT', 'Receipt'), ('PAYMENT', 'Payment'), ('JOURNAL', 'Journal')], max_length=16)),
                ('mode', models.CharField(choices=[('BUSINESS', 'Business'), ('LEGAL', 'Legal')], default='BUSINESS', max_length=16)),
                ('posting_date', models.DateField()),
                ('narration', models.TextField(blank=True, default='')),
                ('is_posted', models.BooleanField(default=False, editable=False)),
                ('posted_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('source_type', models.CharField(blank=True, default='', max_length=64)),
                ('source_id', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vouchers', to='org.business')),
                ('business_source', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='ledger.voucher')),
                ('posted_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='voucher',
            constraint=models.UniqueConstraint(fields=['business', 'number'], name='uniq_voucher_number_per_business'),
        ),
        
        # Create VoucherLine model
        migrations.CreateModel(
            name='VoucherLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('debit', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('credit', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('memo', models.CharField(blank=True, default='', max_length=255)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='voucher_lines', to='ledger.account')),
                ('voucher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='ledger.voucher')),
            ],
        ),
        migrations.AddConstraint(
            model_name='voucherline',
            constraint=models.CheckConstraint(check=~(models.Q(debit__gt=0) & models.Q(credit__gt=0)), name='chk_not_both_debit_and_credit'),
        ),
        migrations.AddConstraint(
            model_name='voucherline',
            constraint=models.CheckConstraint(check=models.Q(debit__gte=0) & models.Q(credit__gte=0), name='chk_debit_credit_non_negative'),
        ),
    ]
