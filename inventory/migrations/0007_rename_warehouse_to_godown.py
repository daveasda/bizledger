# Tally wording: Warehouse -> Godown

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0006_item_is_stock_item"),
    ]

    operations = [
        migrations.RenameModel(old_name="Warehouse", new_name="Godown"),
        migrations.RenameField(
            model_name="stockledgerentry",
            old_name="warehouse",
            new_name="godown",
        ),
    ]
