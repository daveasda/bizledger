# Create "Profit & Loss A/c" primary ledger for each business that has accounts

from django.db import migrations


def create_profit_and_loss_account(apps, schema_editor):
    Account = apps.get_model("ledger", "Account")
    business_ids = Account.objects.values_list("business_id", flat=True).distinct()
    for business_id in business_ids:
        Account.objects.get_or_create(
            business_id=business_id,
            name="Profit & Loss A/c",
            defaults={
                "parent_id": None,
                "is_group": False,
                "is_primary_ledger": True,
                "account_type": "",
                "report_type": "PL",
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0007_account_is_primary_ledger'),
    ]

    operations = [
        migrations.RunPython(create_profit_and_loss_account, noop),
    ]
