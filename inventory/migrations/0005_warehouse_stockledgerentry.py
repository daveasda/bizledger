# Generated manually for Warehouse and StockLedgerEntry (Tally-style stock ledger)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0004_standardrate"),
    ]

    operations = [
        migrations.CreateModel(
            name="Warehouse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warehouses", to="org.business")),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddConstraint(
            model_name="warehouse",
            constraint=models.UniqueConstraint(fields=("business", "name"), name="inventory_warehouse_business_name_uniq"),
        ),
        migrations.CreateModel(
            name="StockLedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("posting_date", models.DateField()),
                ("qty_in", models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ("qty_out", models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ("rate", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("voucher_type", models.CharField(blank=True, default="", max_length=64)),
                ("voucher_id", models.IntegerField(blank=True, null=True)),
                ("is_posted", models.BooleanField(default=False)),
                ("narration", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_ledger_entries", to="org.business")),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_ledger_entries", to="inventory.item")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_ledger_entries", to="inventory.warehouse")),
            ],
            options={
                "ordering": ["-posting_date", "-id"],
                "verbose_name_plural": "Stock ledger entries",
            },
        ),
    ]
