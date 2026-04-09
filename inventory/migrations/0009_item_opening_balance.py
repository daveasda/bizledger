from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0008_remove_stockgroup_can_quantities_be_added"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="opening_qty",
            field=models.DecimalField(
                blank=True, decimal_places=3, max_digits=14, null=True
            ),
        ),
        migrations.AddField(
            model_name="item",
            name="opening_rate",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
        migrations.AddField(
            model_name="item",
            name="opening_value",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
        migrations.AddField(
            model_name="item",
            name="opening_per",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
