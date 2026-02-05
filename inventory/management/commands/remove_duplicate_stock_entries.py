"""
Remove duplicate StockLedgerEntry rows that represent the same movement
(same business, voucher, item, godown, date, qty_in, qty_out).
Keeps the row with the smallest id in each duplicate group; deletes the rest.
Fixes P&L closing stock being 2x (e.g. 1,606,000 instead of 803,000).
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Min

from inventory.models import StockLedgerEntry


class Command(BaseCommand):
    help = "Remove duplicate StockLedgerEntry rows (same voucher+item+godown+qty); keeps one per group."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be deleted, do not delete.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        key_fields = [
            "business_id",
            "voucher_type",
            "voucher_id",
            "item_id",
            "godown_id",
            "posting_date",
            "qty_in",
            "qty_out",
        ]

        dupes = (
            StockLedgerEntry.objects.values(*key_fields)
            .annotate(cnt=Count("id"), min_id=Min("id"))
            .filter(cnt__gt=1)
        )

        dupes_list = list(dupes)
        if not dupes_list:
            self.stdout.write(self.style.SUCCESS("No duplicate StockLedgerEntry rows found."))
            return

        total_to_delete = 0
        for g in dupes_list:
            to_delete = (
                StockLedgerEntry.objects.filter(
                    business_id=g["business_id"],
                    voucher_type=g["voucher_type"],
                    voucher_id=g["voucher_id"],
                    item_id=g["item_id"],
                    godown_id=g["godown_id"],
                    posting_date=g["posting_date"],
                    qty_in=g["qty_in"],
                    qty_out=g["qty_out"],
                )
                .exclude(id=g["min_id"])
                .count()
            )
            total_to_delete += to_delete
            self.stdout.write(
                f"  Duplicate group: voucher_id={g['voucher_id']} item={g['item_id']} "
                f"godown={g['godown_id']} qty_in={g['qty_in']} qty_out={g['qty_out']} "
                f"→ keeping id={g['min_id']}, removing {to_delete} row(s)"
            )

        self.stdout.write(f"\nTotal duplicate rows to remove: {total_to_delete}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no rows deleted. Run without --dry-run to fix."))
            return

        deleted = 0
        for g in dupes_list:
            qs = StockLedgerEntry.objects.filter(
                business_id=g["business_id"],
                voucher_type=g["voucher_type"],
                voucher_id=g["voucher_id"],
                item_id=g["item_id"],
                godown_id=g["godown_id"],
                posting_date=g["posting_date"],
                qty_in=g["qty_in"],
                qty_out=g["qty_out"],
            ).exclude(id=g["min_id"])
            n, _ = qs.delete()
            deleted += n

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} duplicate StockLedgerEntry row(s)."))
