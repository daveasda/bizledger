# Generated manually for StockGroup

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("alias", models.CharField(blank=True, default="", max_length=255)),
                ("can_quantities_be_added", models.BooleanField(default=True, help_text="Can quantities of items be ADDED?")),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_groups", to="org.business")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="inventory.stockgroup")),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddConstraint(
            model_name="stockgroup",
            constraint=models.UniqueConstraint(fields=("business", "name"), name="inventory_stockgroup_business_name_uniq"),
        ),
    ]
