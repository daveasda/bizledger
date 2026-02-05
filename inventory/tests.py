"""
Tests for inventory app. Includes diagnostic test for closing stock variance.
"""
from decimal import Decimal
from datetime import date
from collections import defaultdict

from django.test import TestCase
from django.db.models import Sum

from org.models import Business
from inventory.models import StockLedgerEntry, Godown, Item


def _diagnose_stock_variance():
    """
    Find possible duplicate purchase vouchers (same date + same total amount)
    and report per-item stock contribution. Returns (report_lines, closing_total).
    """
    from ledger.services.stock_valuation import closing_stock_value

    report = []
    businesses = list(Business.objects.all())
    if not businesses:
        return ["No businesses in DB."], Decimal("0.00")

    closing_total = Decimal("0.00")
    for business in businesses:
        report.append(f"=== Business: {business} (id={business.id}) ===")

        # All PURCHASE entries grouped by voucher_id
        purchase_entries = (
            StockLedgerEntry.objects.filter(
                business=business,
                is_posted=True,
                voucher_type="PURCHASE",
            )
            .values("voucher_id", "posting_date")
            .annotate(
                total_amount=Sum("amount", default=Decimal("0")),
                total_qty=Sum("qty_in", default=Decimal("0")),
            )
        )
        by_key = defaultdict(list)
        for e in purchase_entries:
            key = (e["posting_date"], e["total_amount"] or Decimal("0"))
            by_key[key].append(e["voucher_id"])

        # Suspected duplicate vouchers: same (date, amount) with more than one voucher_id
        dupes = [(k, v) for k, v in by_key.items() if len(v) > 1]
        if dupes:
            report.append("  Possible duplicate PURCHASE vouchers (same date + same total amount):")
            for (posting_date, total_amount), voucher_ids in dupes:
                report.append(f"    Date={posting_date} Amount={total_amount} -> voucher_ids={voucher_ids}")
        else:
            report.append("  No obvious duplicate PURCHASE vouchers (same date+amount).")

        # Closing stock total
        period_end = date.today()
        closing_all = closing_stock_value(business, period_end, godown=None)
        closing_total = closing_all
        report.append(f"  Closing stock (all godowns) as of {period_end}: {closing_all}")

        # Per-godown
        for godown in Godown.objects.filter(business=business).order_by("id"):
            closing_g = closing_stock_value(business, period_end, godown=godown)
            if closing_g and closing_g > 0:
                report.append(f"    Godown '{godown.name}': {closing_g}")

        # Per-item breakdown (first godown if any, else all)
        godown = Godown.objects.filter(business=business).order_by("id").first()
        entries = StockLedgerEntry.objects.filter(
            business=business,
            is_posted=True,
            posting_date__lte=period_end,
        )
        if godown is not None:
            entries = entries.filter(godown=godown)
        item_ids = entries.values_list("item_id", flat=True).distinct()
        report.append("  Per-item (qty_in, cost_in, closing_qty, value):")
        for item_id in item_ids:
            item_entries = entries.filter(item_id=item_id)
            qty_in_sum = item_entries.aggregate(s=Sum("qty_in", default=Decimal("0")))["s"] or Decimal("0")
            qty_out_sum = item_entries.aggregate(s=Sum("qty_out", default=Decimal("0")))["s"] or Decimal("0")
            closing_qty = qty_in_sum - qty_out_sum
            if closing_qty <= 0:
                continue
            in_entries = item_entries.filter(qty_in__gt=0)
            cost_in = in_entries.aggregate(s=Sum("amount", default=Decimal("0")))["s"] or Decimal("0")
            qty_in_total = in_entries.aggregate(s=Sum("qty_in", default=Decimal("0")))["s"] or Decimal("0")
            avg_rate = (cost_in / qty_in_total) if qty_in_total and qty_in_total > 0 else Decimal("0")
            value = (closing_qty * avg_rate).quantize(Decimal("0.01"))
            item = Item.objects.filter(pk=item_id).first()
            name = item.name if item else f"id={item_id}"
            report.append(f"    {name}: qty_in={qty_in_sum} cost_in={cost_in} closing_qty={closing_qty} value={value}")

        report.append("")

    return report, closing_total


class StockVarianceDiagnosticTest(TestCase):
    """
    Runs stock variance diagnosis: finds possible duplicate vouchers
    and reports closing stock and per-item breakdown. Prints to stdout.
    """

    def test_diagnose_stock_variance(self):
        report_lines, closing_total = _diagnose_stock_variance()
        for line in report_lines:
            print(line)
        # Test always passes; diagnosis is in the printed report
        self.assertIsNotNone(closing_total)
