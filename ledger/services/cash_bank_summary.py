"""
Cash/Bank Summary: closing balance of Cash-in-hand and Bank Accounts groups,
with ledgers listed under each and a Grand Total.
"""
from decimal import Decimal
from collections import defaultdict
from datetime import date

from ledger.models import Account
from ledger.services.balance_sheet import (
    _ledger_closing_balances,
    _descendant_ledger_ids,
)

# Group names to include (case-insensitive match)
CASH_BANK_GROUP_NAMES = ("Cash-in-hand", "Bank Accounts")


def compute_cash_bank_summary(business, end_date=None):
    """
    Returns:
    {
      "sections": [
        {
          "name": "Cash-in-hand",
          "group_dr": Decimal,
          "group_cr": Decimal,
          "ledgers": [{"name": str, "closing_dr": Decimal, "closing_cr": Decimal}],
        },
        { "name": "Bank Accounts", ... },
      ],
      "grand_total_dr": Decimal,
      "grand_total_cr": Decimal,
      "end_date": date | None,
    }
    """
    as_of = end_date if end_date else date.today()
    closing_net_by_ledger = _ledger_closing_balances(business, end_date=as_of)

    # closing_net -> (debit col, credit col) for display
    def net_to_dr_cr(net):
        n = net.quantize(Decimal("0.01"))
        if n >= 0:
            return (n, Decimal("0.00"))
        return (Decimal("0.00"), (-n).quantize(Decimal("0.01")))

    closing_dr_cr_by_ledger = {
        lid: net_to_dr_cr(closing_net_by_ledger[lid])
        for lid in closing_net_by_ledger
    }

    # Build tree
    accounts = Account.objects.filter(business=business).values(
        "id", "parent_id", "name", "is_group"
    )
    children_map = defaultdict(list)
    account_map = {}
    for a in accounts:
        children_map[a["parent_id"]].append(a["id"])
        account_map[a["id"]] = a

    # Find Cash-in-hand and Bank Accounts groups (case-insensitive)
    name_lower_to_id = {}
    for aid, a in account_map.items():
        if not a.get("is_group"):
            continue
        name = (a.get("name") or "").strip().lower()
        if name == "cash-in-hand":
            name_lower_to_id["cash-in-hand"] = aid
        elif name == "bank accounts":
            name_lower_to_id["bank accounts"] = aid

    section_order = ["cash-in-hand", "bank accounts"]
    section_ids = [
        name_lower_to_id[name]
        for name in section_order
        if name in name_lower_to_id
    ]

    sections = []
    grand_total_dr = Decimal("0.00")
    grand_total_cr = Decimal("0.00")

    for group_id in section_ids:
        acc = account_map.get(group_id)
        if not acc:
            continue
        group_name = acc.get("name") or "—"
        ledger_ids = _descendant_ledger_ids(group_id, children_map, account_map)
        group_dr = sum(
            closing_dr_cr_by_ledger.get(lid, (Decimal("0.00"), Decimal("0.00")))[0]
            for lid in ledger_ids
        ).quantize(Decimal("0.01"))
        group_cr = sum(
            closing_dr_cr_by_ledger.get(lid, (Decimal("0.00"), Decimal("0.00")))[1]
            for lid in ledger_ids
        ).quantize(Decimal("0.01"))

        # Direct child ledgers (no sub-groups) for display
        direct_ledgers = Account.objects.filter(
            business=business,
            parent_id=group_id,
            is_group=False,
        ).order_by("name")

        ledgers = []
        for ledger in direct_ledgers:
            dr, cr = closing_dr_cr_by_ledger.get(
                ledger.id, (Decimal("0.00"), Decimal("0.00"))
            )
            ledgers.append({
                "name": ledger.name,
                "closing_dr": dr.quantize(Decimal("0.01")),
                "closing_cr": cr.quantize(Decimal("0.01")),
            })

        sections.append({
            "name": group_name,
            "group_dr": group_dr,
            "group_cr": group_cr,
            "ledgers": ledgers,
        })
        grand_total_dr += group_dr
        grand_total_cr += group_cr

    return {
        "sections": sections,
        "grand_total_dr": grand_total_dr.quantize(Decimal("0.01")),
        "grand_total_cr": grand_total_cr.quantize(Decimal("0.01")),
        "end_date": as_of,
    }
