"""
Balance Sheet: Liabilities (left) and Assets (right) with group summary balances.
Profit & Loss A/c row shows gross profit from P&L report.
"""
from decimal import Decimal
from collections import defaultdict

from django.db.models import Sum

from ledger.models import Account, VoucherLine

# Standard root group names (top-level buckets like Assets/Liabilities/etc.)
# Primary groups like "Capital Account", "Loans (Liability)", "Current Liabilities"
# will typically be additional root groups with the same root_type.
STANDARD_ROOT_NAMES = ("Assets", "Liabilities", "Income", "Expenses")


def _ledger_closing_balances(business, end_date=None):
    """Return dict account_id -> closing_net (Decimal) for all ledgers."""
    ledgers = Account.objects.filter(business=business, is_group=False)
    qs = VoucherLine.objects.filter(
        account__in=ledgers,
        voucher__business=business,
        voucher__is_posted=True,
    )
    if end_date:
        qs = qs.filter(voucher__posting_date__lte=end_date)
    agg = (
        qs.values("account_id")
        .annotate(total_dr=Sum("debit"), total_cr=Sum("credit"))
    )
    agg_by_account = {
        r["account_id"]: (
            r["total_dr"] or Decimal("0.00"),
            r["total_cr"] or Decimal("0.00"),
        )
        for r in agg
    }
    result = {}
    for ledger in ledgers:
        op_bal = ledger.opening_balance or Decimal("0.00")
        op_type = ledger.opening_balance_type or "DR"
        opening_net = -op_bal if op_type == "CR" else op_bal
        total_dr, total_cr = agg_by_account.get(ledger.id, (Decimal("0.00"), Decimal("0.00")))
        result[ledger.id] = (opening_net + total_dr - total_cr).quantize(Decimal("0.01"))
    return result


def _descendant_ledger_ids(group_id, children_map, account_map):
    """Return set of ledger IDs that are descendants of the given group."""
    ids = set()
    for child_id in children_map.get(group_id, []):
        acc = account_map.get(child_id)
        if not acc:
            continue
        if acc.get("is_group"):
            ids |= _descendant_ledger_ids(child_id, children_map, account_map)
        else:
            ids.add(child_id)
    return ids


def compute_balance_sheet(business, end_date=None):
    """
    Returns:
    {
      "liability_rows": [(group_name, amount), ...],   # amount >= 0
      "asset_rows": [(group_name, amount), ...],
      "gross_profit": Decimal,   # for Profit & Loss A/c row
      "total_liabilities": Decimal,
      "total_assets": Decimal,
    }
    """
    from ledger.services.pnl import compute_profit_and_loss

    closing_by_ledger = _ledger_closing_balances(business, end_date)

    # Build tree: parent_id -> list of child accounts; and account_id -> {name, is_group, root_type}
    accounts = Account.objects.filter(business=business).values("id", "parent_id", "name", "is_group", "root_type")
    children_map = defaultdict(list)
    account_map = {}
    for a in accounts:
        children_map[a["parent_id"]].append(a["id"])
        account_map[a["id"]] = a

    # Root groups (parent_id is None) that participate in the Balance Sheet
    root_ids = children_map.get(None, [])

    # Prefer non-standard primary groups (e.g. Capital Account, Loans, Current Liabilities, Current Assets)
    liability_root_ids = [
        aid
        for aid in root_ids
        if account_map.get(aid, {}).get("root_type") == "LIABILITY"
        and (account_map.get(aid, {}).get("name") or "") not in STANDARD_ROOT_NAMES
    ]
    asset_root_ids = [
        aid
        for aid in root_ids
        if account_map.get(aid, {}).get("root_type") == "ASSET"
        and (account_map.get(aid, {}).get("name") or "") not in STANDARD_ROOT_NAMES
    ]

    # Fallback: if no primary groups, fall back to standard roots
    if not liability_root_ids:
        liability_root_ids = [
            aid for aid in root_ids if account_map.get(aid, {}).get("root_type") == "LIABILITY"
        ]
    if not asset_root_ids:
        asset_root_ids = [
            aid for aid in root_ids if account_map.get(aid, {}).get("root_type") == "ASSET"
        ]

    def group_balances(root_ids, sign_for_display=1):
        """
        sign_for_display:
          -  1 = assets (debit balance positive)
          - -1 = liabilities (credit balance positive)
        Each root_id is treated as one top-level row (e.g. Capital Account, Current Liabilities).
        """
        rows = []
        for root_id in sorted(root_ids, key=lambda i: (account_map.get(i) or {}).get("name") or ""):
            acc = account_map.get(root_id)
            if not acc or not acc.get("is_group"):
                continue
            name = acc.get("name") or "—"
            ledger_ids = _descendant_ledger_ids(root_id, children_map, account_map)
            total = sum(closing_by_ledger.get(lid, Decimal("0.00")) for lid in ledger_ids)
            total = (sign_for_display * total).quantize(Decimal("0.01"))
            rows.append((name, total))
        return rows

    # Liabilities: credit balance is normal, so show as positive (multiply by -1)
    liability_rows = group_balances(liability_root_ids, sign_for_display=-1)
    # Assets: debit balance is normal (already positive)
    asset_rows = group_balances(asset_root_ids, sign_for_display=1)

    # Gross profit from P&L (for Profit & Loss A/c row)
    pnl_data = compute_profit_and_loss(
        business,
        start_date=None,
        end_date=end_date,
        godown=None,
    )
    gross_profit = (pnl_data.get("gross_profit") or Decimal("0.00")).quantize(Decimal("0.01"))

    # Profit & Loss A/c row shows gross profit (positive = profit, negative = loss)
    total_liabilities = sum(amt for _, amt in liability_rows) + gross_profit
    total_assets = sum(amt for _, amt in asset_rows)

    return {
        "liability_rows": liability_rows,
        "asset_rows": asset_rows,
        "gross_profit": gross_profit,
        "total_liabilities": total_liabilities.quantize(Decimal("0.01")),
        "total_assets": total_assets.quantize(Decimal("0.01")),
    }
