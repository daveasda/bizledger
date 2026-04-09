from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0007_rename_warehouse_to_godown"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="stockgroup",
            name="can_quantities_be_added",
        ),
    ]

