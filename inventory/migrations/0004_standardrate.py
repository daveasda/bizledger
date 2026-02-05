# Generated manually for StandardRate

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_unitofmeasure_item_updates"),
    ]

    operations = [
        migrations.CreateModel(
            name="StandardRate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rate_type", models.CharField(choices=[("COST", "Cost"), ("SELLING", "Selling")], max_length=16)),
                ("applicable_from", models.DateField()),
                ("rate", models.DecimalField(decimal_places=2, max_digits=14)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="standard_rates", to="inventory.item")),
            ],
            options={
                "ordering": ["-applicable_from"],
            },
        ),
        migrations.AddConstraint(
            model_name="standardrate",
            constraint=models.UniqueConstraint(fields=("item", "rate_type", "applicable_from"), name="inventory_standardrate_item_type_date_uniq"),
        ),
    ]
