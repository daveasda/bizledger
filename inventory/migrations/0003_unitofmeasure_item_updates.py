# Generated manually for UnitOfMeasure and Item updates

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0002_stockgroup"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnitOfMeasure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("unit_type", models.CharField(choices=[("SIMPLE", "Simple"), ("COMPOUND", "Compound")], default="SIMPLE", max_length=16)),
                ("symbol", models.CharField(max_length=32)),
                ("formal_name", models.CharField(blank=True, default="", max_length=100)),
                ("decimal_places", models.PositiveSmallIntegerField(default=0)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="units_of_measure", to="org.business")),
            ],
            options={
                "ordering": ["symbol"],
            },
        ),
        migrations.AddConstraint(
            model_name="unitofmeasure",
            constraint=models.UniqueConstraint(fields=("business", "symbol"), name="inventory_unit_business_symbol_uniq"),
        ),
        migrations.AddField(
            model_name="item",
            name="alias",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AlterField(
            model_name="item",
            name="name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="item",
            name="stock_group",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="items", to="inventory.stockgroup"),
        ),
        migrations.AddField(
            model_name="item",
            name="unit",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="items", to="inventory.unitofmeasure"),
        ),
    ]
