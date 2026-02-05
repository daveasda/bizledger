"""
Profit & Loss computation: accounting + inventory-integrated (Tally-style).
- Uses posted VoucherLines for Sales, Purchases, Other Income, Indirect Expense.
- Uses StockLedgerEntry for Opening Stock and Closing Stock (average-rate valuation).
- COGS = Opening Stock + Purchases − Closing Stock
- Gross Profit = Sales − COGS
- Net Profit = Gross Profit − Indirect Expenses + Other Income
"""
from decimal import Decimal
from datetime import date

from django.db.models import Sum

from ledger.models import Account, VoucherLine

# Name hints when hierarchy says non–P&L (e.g. ledger under Assets). Use sparingly.
_INCOME_NAME_HINTS = ("sales", "revenue", "income")
_EXPENSE_NAME_HINTS = ("purchase", "rent", "salary", "electricity", "wages", "expense")
# Split trading P&L: Sales vs Other Income, Purchase vs Indirect Expense
_SALES_NAME_HINTS = ("sales",)
_PURCHASE_NAME_HINTS = ("purchase",)


def _resolve_root_types(business, account_ids):
    """
    For each account id, walk parent chain to root; return root's root_type.
    Uses single bulk fetch to avoid N+1.
    """
    if not account_ids:
        return {}
    accounts = {
        a["id"]: {"parent_id": a["parent_id"], "root_type": (a["root_type"] or "").strip() or None}
        for a in Account.objects.filter(business=business).values("id", "parent_id", "root_type")
    }
    cache = {}

    def walk(aid, seen):
        if aid in cache:
            return cache[aid]
        if aid in seen:
            cache[aid] = None
            return None
        seen.add(aid)
        acc = accounts.get(aid)
        if not acc:
            cache[aid] = None
            return None
        pid = acc["parent_id"]
        rt = acc["root_type"]
        if pid is None:
            cache[aid] = rt
            return rt
        parent_rt = walk(pid, seen)
        cache[aid] = parent_rt
        return parent_rt

    for aid in account_ids:
        if aid not in cache:
            walk(aid, set())
    return cache


def compute_profit_and_loss(
    business,
    start_date=None,
    end_date=None,
    debug=False,
    godown=None,
    opening_stock_override=None,
    closing_stock_override=None,
):
    """
    Inventory-integrated P&L (Tally-style).
    godown: optional; when set, opening/closing stock use only that godown (matches Tally primary godown).
    opening_stock_override, closing_stock_override: optional Decimals; when set, use instead of inventory valuation (e.g. to match Tally book value 803000).

    Returns:
    {
      "sales": [(account_name, amount), ...],
      "purchases": [(account_name, amount), ...],
      "other_income": [(account_name, amount), ...],
      "indirect_expense": [(account_name, amount), ...],
      "sales_total": Decimal,
      "purchase_total": Decimal,
      "other_income_total": Decimal,
      "indirect_expense_total": Decimal,
      "opening_stock_value": Decimal,
      "closing_stock_value": Decimal,
      "cogs": Decimal,           # Opening + Purchases − Closing
      "gross_profit": Decimal,  # Sales − COGS
      "net_profit": Decimal,    # Gross Profit − Indirect Expense + Other Income
      "total_income": Decimal,   # sales_total + other_income_total (legacy)
      "total_expense": Decimal,  # purchase_total + indirect_expense_total (legacy)
      "income": [...], "expense": [...],  # legacy flat lists for backward compat
    }
    If debug=True, also returns "debug_rows".
    """
    from ledger.services.stock_valuation import closing_stock_value, opening_stock_value

    qs = VoucherLine.objects.filter(
        voucher__business=business,
        voucher__is_posted=True,
        account__is_group=False,
    )

    if start_date:
        qs = qs.filter(voucher__posting_date__gte=start_date)
    if end_date:
        qs = qs.filter(voucher__posting_date__lte=end_date)

    rows = (
        qs.values(
            "account_id",
            "account__name",
            "account__root_type",
            "account__parent__root_type",
        )
        .annotate(
            dr=Sum("debit", default=Decimal("0.00")),
            cr=Sum("credit", default=Decimal("0.00")),
        )
        .order_by("account__name")
    )

    account_ids = {r["account_id"] for r in rows}
    root_types_walk = _resolve_root_types(business, account_ids)

    sales = []
    purchases = []
    other_income = []
    indirect_expense = []
    sales_total = Decimal("0.00")
    purchase_total = Decimal("0.00")
    other_income_total = Decimal("0.00")
    indirect_expense_total = Decimal("0.00")
    debug_rows = [] if debug else None

    for r in rows:
        rt_acc = (r.get("account__root_type") or "").strip() or None
        rt_parent = (r.get("account__parent__root_type") or "").strip() or None
        rt_walk = root_types_walk.get(r["account_id"])
        if rt_acc in ("INCOME", "EXPENSE"):
            root_type = rt_acc
        elif rt_parent in ("INCOME", "EXPENSE"):
            root_type = rt_parent
        else:
            root_type = rt_walk

        name = (r.get("account__name") or "").strip() or "?"
        name_lower = name.lower()

        if not root_type or root_type not in ("INCOME", "EXPENSE"):
            if any(h in name_lower for h in _INCOME_NAME_HINTS):
                root_type = "INCOME"
            elif any(h in name_lower for h in _EXPENSE_NAME_HINTS):
                root_type = "EXPENSE"
        dr = r["dr"] or Decimal("0.00")
        cr = r["cr"] or Decimal("0.00")

        if debug:
            debug_rows.append({
                "account_id": r["account_id"],
                "name": name,
                "dr": dr,
                "cr": cr,
                "root_type": root_type or "(none)",
            })

        if not root_type or root_type not in ("INCOME", "EXPENSE"):
            if debug:
                debug_rows[-1]["classification"] = "skipped (not INCOME/EXPENSE)"
            continue

        if root_type == "INCOME":
            amt = cr - dr
            if amt == 0:
                if debug:
                    debug_rows[-1]["classification"] = "INCOME (amt=0, skipped)"
                continue
            if any(h in name_lower for h in _SALES_NAME_HINTS):
                sales.append((name, amt))
                sales_total += amt
                if debug:
                    debug_rows[-1]["classification"] = f"Sales → {amt}"
            else:
                other_income.append((name, amt))
                other_income_total += amt
                if debug:
                    debug_rows[-1]["classification"] = f"Other Income → {amt}"
        else:
            amt = dr - cr
            if amt == 0:
                if debug:
                    debug_rows[-1]["classification"] = "EXPENSE (amt=0, skipped)"
                continue
            if any(h in name_lower for h in _PURCHASE_NAME_HINTS):
                purchases.append((name, amt))
                purchase_total += amt
                if debug:
                    debug_rows[-1]["classification"] = f"Purchase → {amt}"
            else:
                indirect_expense.append((name, amt))
                indirect_expense_total += amt
                if debug:
                    debug_rows[-1]["classification"] = f"Indirect Expense → {amt}"

    # Stock valuation: as of end_date (or today if no end_date); optional godown; overrides take precedence (e.g. ?closing_stock=803000 to match Tally)
    period_end = end_date if end_date else date.today()
    if opening_stock_override is not None:
        opening_stock = Decimal(str(opening_stock_override)).quantize(Decimal("0.01"))
    else:
        opening_stock = opening_stock_value(business, start_date, godown=godown)
    if closing_stock_override is not None:
        closing_stock = Decimal(str(closing_stock_override)).quantize(Decimal("0.01"))
    else:
        closing_stock = closing_stock_value(business, period_end, godown=godown)

    # COGS = Opening Stock + Purchases − Closing Stock
    cogs = (opening_stock + purchase_total - closing_stock).quantize(Decimal("0.01"))
    # Gross Profit = Sales − COGS
    gross_profit = (sales_total - cogs).quantize(Decimal("0.01"))
    # Net Profit = Gross Profit − Indirect Expenses + Other Income
    net_profit = (gross_profit - indirect_expense_total + other_income_total).quantize(Decimal("0.01"))

    total_income = sales_total + other_income_total
    total_expense = purchase_total + indirect_expense_total
    # Legacy flat lists (all income, all expense) for any old template
    income = sales + other_income
    expense = [(n, a) for n, a in purchases] + [(n, a) for n, a in indirect_expense]
    # Tally-style: both sides show same total; balancing figure is Nett Profit
    # Total (Credit) = Sales + Closing Stock
    total_credit = (sales_total + closing_stock).quantize(Decimal("0.01"))
    # Total (Debit) = Opening + Purchases + Indirect + Nett Profit (must equal total_credit)
    total_debit = (
        opening_stock + purchase_total + indirect_expense_total + net_profit
    ).quantize(Decimal("0.01"))

    out = {
        "sales": sales,
        "purchases": purchases,
        "other_income": other_income,
        "indirect_expense": indirect_expense,
        "sales_total": sales_total,
        "purchase_total": purchase_total,
        "other_income_total": other_income_total,
        "indirect_expense_total": indirect_expense_total,
        "opening_stock_value": opening_stock,
        "closing_stock_value": closing_stock,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "total_income": total_income,
        "total_expense": total_expense,
        "balance_total": total_credit,  # legacy; same as total_credit
        "total_debit": total_debit,
        "total_credit": total_credit,
        "income": income,
        "expense": expense,
    }
    if debug:
        out["debug_rows"] = debug_rows
    return out
