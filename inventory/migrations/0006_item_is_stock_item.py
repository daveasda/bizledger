# Add is_stock_item to Item (Tally: Stock Items master)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0005_warehouse_stockledgerentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="is_stock_item",
            field=models.BooleanField(default=True),
        ),
    ]
