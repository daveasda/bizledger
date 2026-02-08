"""
Fix PURCHASE/SALES vouchers that used Cash instead of Purchase/Sales ledger,
so P&L shows correct Sales and COGS.

Finds vouchers where:
- PURCHASE: debit line goes to Cash (or non-EXPENSE) instead of Purchase A/C
- SALES: credit line goes to Cash (or non-INCOME) instead of Sales A/C

Replaces with correct Purchase/Sales ledger. Run with --dry-run first.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from ledger.models import Voucher, VoucherLine, Account, VoucherType


class Command(BaseCommand):
    help = "Fix PURCHASE/SALES vouchers that used wrong accounts (e.g. Cash instead of Purchase/Sales A/C)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report what would be changed.")
        parser.add_argument("--business", type=int, default=None, help="Business ID (default: first).")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        bid = options["business"]
        from org.models import Business
        if bid:
            businesses = [Business.objects.get(pk=bid)]
        else:
            businesses = list(Business.objects.all())
        if not businesses:
            self.stdout.write("No businesses found.")
            return

        for business in businesses:
            purchase_ledger = Account.objects.filter(
                business=business, is_group=False
            ).filter(Q(root_type="EXPENSE") | Q(name__icontains="purchase")).first()
            sales_ledger = Account.objects.filter(
                business=business, is_group=False
            ).filter(Q(root_type="INCOME") | Q(name__icontains="sales")).first()
            if not purchase_ledger or not sales_ledger:
                self.stdout.write(
                    f"Business {business}: Need Purchase and Sales ledger accounts. "
                    f"purchase={purchase_ledger}, sales={sales_ledger}"
                )
                continue

            for v in Voucher.objects.filter(business=business, is_posted=True, voucher_type__in=[VoucherType.PURCHASE, VoucherType.SALES]):
                if v.voucher_type == VoucherType.PURCHASE:
                    # Find debit line not to Purchase ledger
                    wrong = v.lines.filter(debit__gt=0).exclude(account=purchase_ledger).first()
                    if wrong and wrong.account_id != purchase_ledger.id:
                        self.stdout.write(
                            f"Voucher {v.id} (PURCHASE): Line account={wrong.account.name} (dr={wrong.debit}) "
                            f"-> should be {purchase_ledger.name}"
                        )
                        if not dry_run:
                            with transaction.atomic():
                                v.is_posted = False
                                v.save(update_fields=["is_posted"])
                                wrong.account = purchase_ledger
                                wrong.save(update_fields=["account_id"])
                                v.post()
                            self.stdout.write(self.style.SUCCESS(f"  Fixed."))
                else:
                    # SALES: find credit line not to Sales ledger
                    wrong = v.lines.filter(credit__gt=0).exclude(account=sales_ledger).first()
                    if wrong and wrong.account_id != sales_ledger.id:
                        self.stdout.write(
                            f"Voucher {v.id} (SALES): Line account={wrong.account.name} (cr={wrong.credit}) "
                            f"-> should be {sales_ledger.name}"
                        )
                        if not dry_run:
                            with transaction.atomic():
                                v.is_posted = False
                                v.save(update_fields=["is_posted"])
                                wrong.account = sales_ledger
                                wrong.save(update_fields=["account_id"])
                                v.post()
                            self.stdout.write(self.style.SUCCESS(f"  Fixed."))
