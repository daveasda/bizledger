from decimal import Decimal
from django.db import migrations
from django.utils import timezone


def _fy_start(d):
    if d.month >= 4:
        return d.replace(month=4, day=1)
    return d.replace(year=d.year - 1, month=4, day=1)


def forwards(apps, schema_editor):
    Item = apps.get_model("inventory", "Item")
    Godown = apps.get_model("inventory", "Godown")
    StockLedgerEntry = apps.get_model("inventory", "StockLedgerEntry")

    today = timezone.localdate()
    posting_date = _fy_start(today)

    for item in Item.objects.all().iterator():
        qty = item.opening_qty or Decimal("0")
        seed_qs = StockLedgerEntry.objects.filter(
            business_id=item.business_id,
            item_id=item.id,
            voucher_type="OPENING",
            voucher_id__isnull=True,
            is_posted=True,
        )

        if qty <= 0:
            seed_qs.delete()
            continue

        godown = Godown.objects.filter(business_id=item.business_id).order_by("id").first()
        if godown is None:
            godown = Godown.objects.create(business_id=item.business_id, name="Main Location")

        rate = item.opening_rate or Decimal("0")
        amount = item.opening_value
        if amount is None:
            amount = (qty * rate).quantize(Decimal("0.01"))

        seed = seed_qs.filter(godown_id=godown.id).order_by("id").first()
        if seed:
            seed.posting_date = posting_date
            seed.qty_in = qty
            seed.qty_out = Decimal("0")
            seed.rate = rate
            seed.amount = amount
            seed.narration = "Opening balance seed (auto)"
            seed.save(update_fields=["posting_date", "qty_in", "qty_out", "rate", "amount", "narration", "updated_at"])
        else:
            seed = StockLedgerEntry.objects.create(
                business_id=item.business_id,
                posting_date=posting_date,
                item_id=item.id,
                godown_id=godown.id,
                qty_in=qty,
                qty_out=Decimal("0"),
                rate=rate,
                amount=amount,
                voucher_type="OPENING",
                voucher_id=None,
                is_posted=True,
                narration="Opening balance seed (auto)",
            )

        seed_qs.exclude(pk=seed.pk).delete()


def backwards(apps, schema_editor):
    StockLedgerEntry = apps.get_model("inventory", "StockLedgerEntry")
    StockLedgerEntry.objects.filter(
        voucher_type="OPENING",
        voucher_id__isnull=True,
        is_posted=True,
        narration="Opening balance seed (auto)",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0009_item_opening_balance"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

