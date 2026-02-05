"""
Stock valuation for P&L: Opening Stock and Closing Stock values.
Uses posted StockLedgerEntry only. Valuation = average rate (cost of goods received).
"""
from decimal import Decimal
from datetime import timedelta

from django.db.models import Sum


def closing_stock_value(business, as_of_date, godown=None):
    """
    Total value of inventory as of as_of_date (inclusive).
    Per item: closing_qty = sum(qty_in) - sum(qty_out); avg_rate = sum(amount) for in / sum(qty_in); value = closing_qty * avg_rate.
    If godown is set, only entries for that godown are included (Tally-style: primary godown for P&L).
    Returns Decimal (0 if no inventory or no entries).
    """
    from inventory.models import StockLedgerEntry

    if not as_of_date:
        return Decimal("0.00")

    entries = StockLedgerEntry.objects.filter(
        business=business,
        is_posted=True,
        posting_date__lte=as_of_date,
    )
    if godown is not None:
        entries = entries.filter(godown=godown)

    # Per item: balance qty and total cost in (for average rate)
    # Use set() so each item is valued once (some DB/ORM combos can return duplicate ids from .distinct())
    item_ids = list(set(entries.values_list("item_id", flat=True)))
    total_value = Decimal("0.00")

    for item_id in item_ids:
        item_entries = entries.filter(item_id=item_id)
        qty_in_sum = item_entries.aggregate(s=Sum("qty_in", default=Decimal("0")))["s"] or Decimal("0")
        qty_out_sum = item_entries.aggregate(s=Sum("qty_out", default=Decimal("0")))["s"] or Decimal("0")
        closing_qty = qty_in_sum - qty_out_sum
        if closing_qty <= 0:
            continue
        # Average rate from receipts (qty_in > 0)
        in_entries = item_entries.filter(qty_in__gt=0)
        cost_in = in_entries.aggregate(s=Sum("amount", default=Decimal("0")))["s"] or Decimal("0")
        qty_in_total = in_entries.aggregate(s=Sum("qty_in", default=Decimal("0")))["s"] or Decimal("0")
        if qty_in_total and qty_in_total > 0:
            avg_rate = cost_in / qty_in_total
            total_value += (closing_qty * avg_rate).quantize(Decimal("0.01"))

    return total_value


def opening_stock_value(business, period_start_date, godown=None):
    """
    Opening stock = closing stock as of the day before period_start_date.
    If period_start_date is None, return 0 (no opening).
    godown: optional, same as closing_stock_value (filter by godown for Tally-style P&L).
    """
    if not period_start_date:
        return Decimal("0.00")
    day_before = period_start_date - timedelta(days=1)
    return closing_stock_value(business, day_before, godown=godown)


def closing_stock_value_per_godown(business, as_of_date):
    """
    Returns [(godown, value), ...] for each godown that has stock, plus total.
    Used for report breakdown and godown selector.
    """
    try:
        from inventory.models import Godown
    except ImportError:
        return [], Decimal("0.00")
    godowns = Godown.objects.filter(business=business).order_by("id")
    result = []
    total = Decimal("0.00")
    for g in godowns:
        val = closing_stock_value(business, as_of_date, godown=g)
        if val and val > 0:
            result.append((g, val))
            total += val
    return result, total
