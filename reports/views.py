from decimal import Decimal
from datetime import date
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ledger.services.balance_sheet import compute_balance_sheet
from ledger.services.cash_bank_summary import compute_cash_bank_summary
from ledger.services.pnl import compute_profit_and_loss
from ledger.services.stock_valuation import closing_stock_value_per_godown
from ledger.utils import get_active_business_id
from org.models import Business

try:
    from inventory.models import Godown
except ImportError:
    Godown = None


@login_required
def home(request):
    """Dashboard: current mode, quick actions, and embedded Ledger + Inventory displays."""
    bid = get_active_business_id(request)
    if not bid:
        return redirect(reverse("org:select_business"))
    business = get_object_or_404(Business, id=bid)

    from ledger.models import Account
    ledgers = Account.objects.filter(business=business, is_group=False).order_by("name")
    sales_ledger = (
        Account.objects.filter(business=business, is_group=False, name="Sales Ledger").first()
        or Account.objects.filter(business=business, is_group=False, name__iexact="sales").first()
    )
    purchase_ledger = (
        Account.objects.filter(business=business, is_group=False, name="Purchase A/C").first()
        or Account.objects.filter(business=business, is_group=False, name__iexact="purchase").first()
    )
    sales_group = Account.objects.filter(business=business, is_group=True, name="Sales").first()
    purchase_group = Account.objects.filter(business=business, is_group=True, name="Purchase").first()

    # Current local datetime for dashboard display (uses Django TIME_ZONE setting)
    now_local = timezone.localtime(timezone.now())

    try:
        from inventory.models import StockGroup, Item, UnitOfMeasure
        groups = StockGroup.objects.filter(business=business).order_by("name")
        items = Item.objects.filter(business=business).order_by("sku")
        units = UnitOfMeasure.objects.filter(business=business).order_by("symbol")
    except ImportError:
        groups = items = units = []

    return render(request, "reports/home.html", {
        "business": business,
        "ledgers": ledgers,
        "sales_ledger": sales_ledger,
        "purchase_ledger": purchase_ledger,
        "sales_group": sales_group,
        "purchase_group": purchase_group,
        "groups": groups,
        "items": items,
        "units": units,
        "now": now_local,
    })


@login_required
def reports_list(request):
    """Reports index: list of available reports (e.g. Profit and Loss A/C)."""
    return render(request, "reports/list.html")


@login_required
def pnl(request):
    return render(request, "reports/pnl.html")


def _parse_date(s):
    """Parse YYYY-MM-DD from GET param; return date or None."""
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip())
    except (ValueError, TypeError):
        return None


@login_required
def profit_and_loss(request):
    """Profit & Loss A/c — Inventory-integrated (Tally-style): Sales, Purchases, Opening/Closing Stock, COGS, Gross/Net Profit."""
    bid = get_active_business_id(request)
    if not bid:
        return redirect(reverse("org:select_business"))
    business = get_object_or_404(Business, id=bid)

    debug = request.GET.get("debug") in ("1", "true", "yes")
    start_date = _parse_date(request.GET.get("start_date"))
    end_date = _parse_date(request.GET.get("end_date"))
    period_end = end_date if end_date else date.today()

    # Godown filter: ?godown=all or omit = all godowns; ?godown=<id> = that godown only
    godown = None
    godown_param = request.GET.get("godown")
    if Godown and godown_param:
        if str(godown_param).lower() == "all":
            godown = None
        else:
            try:
                gid = int(godown_param)
                godown = Godown.objects.filter(business=business, id=gid).first()
            except (ValueError, TypeError):
                pass

    # Override stock from ledger/book value: ?closing_stock=803000 & ?opening_stock=0 to match Tally when inventory valuation differs
    def _parse_decimal_param(name):
        val = request.GET.get(name)
        if val is None or val == "":
            return None
        try:
            return Decimal(str(val).strip())
        except (ValueError, TypeError, Exception):
            return None

    opening_stock_override = _parse_decimal_param("opening_stock")
    closing_stock_override = _parse_decimal_param("closing_stock")

    data = compute_profit_and_loss(
        business,
        start_date=start_date,
        end_date=end_date,
        debug=debug,
        godown=godown,
        opening_stock_override=opening_stock_override,
        closing_stock_override=closing_stock_override,
    )
    data["business"] = business
    data["godown"] = godown
    data["debug"] = debug
    data["start_date"] = start_date
    data["end_date"] = end_date
    data["closing_stock_override"] = closing_stock_override
    data["opening_stock_override"] = opening_stock_override

    # Per-godown closing stock breakdown (so user can pick one and see 803000)
    if Godown:
        closing_per_godown, _ = closing_stock_value_per_godown(business, period_end)
        data["closing_stock_per_godown"] = closing_per_godown
        data["godowns"] = list(Godown.objects.filter(business=business).order_by("id"))
    else:
        data["closing_stock_per_godown"] = []
        data["godowns"] = []

    # Query string for "Opening Stock" / "Closing Stock" links to Stock Summary (same godown/date range)
    qs_parts = []
    if godown:
        qs_parts.append(f"godown={godown.id}")
    if start_date:
        qs_parts.append(f"date_from={start_date:%Y-%m-%d}")
    if end_date:
        qs_parts.append(f"date_to={end_date:%Y-%m-%d}")
    data["stock_summary_query"] = "?" + "&".join(qs_parts) if qs_parts else ""

    return render(request, "reports/profit_and_loss.html", data)


@login_required
def balance_sheet(request):
    """Balance Sheet: Liabilities (left) and Assets (right). Profit & Loss A/c row shows gross profit from P&L. Row names link to Group Summary or P&L."""
    bid = get_active_business_id(request)
    if not bid:
        return redirect(reverse("org:select_business"))
    business = get_object_or_404(Business, id=bid)
    end_date = _parse_date(request.GET.get("end_date"))
    data = compute_balance_sheet(business, end_date=end_date)

    # Add link_url to each row: groups → Group Summary, Profit & Loss A/c → P&L report
    liability_rows = [
        {"name": r["name"], "amount": r["amount"], "link_url": reverse("ledger:group_summary", args=[r["group_id"]])}
        for r in data["liability_rows"]
    ]
    liability_rows.append({
        "name": "Profit & Loss A/c",
        "amount": data["gross_profit"],
        "link_url": reverse("reports:profit_and_loss"),
    })
    asset_rows = [
        {"name": r["name"], "amount": r["amount"], "link_url": reverse("ledger:group_summary", args=[r["group_id"]])}
        for r in data["asset_rows"]
    ]

    data["business"] = business
    data["end_date"] = end_date
    data["liability_rows"] = liability_rows
    data["asset_rows"] = asset_rows
    return render(request, "reports/balance_sheet.html", data)


@login_required
def cash_bank_summary(request):
    """Cash/Bank Summary: closing balance of Cash-in-hand and Bank Accounts groups with ledgers and Grand Total."""
    bid = get_active_business_id(request)
    if not bid:
        return redirect(reverse("org:select_business"))
    business = get_object_or_404(Business, id=bid)
    end_date = _parse_date(request.GET.get("end_date"))
    data = compute_cash_bank_summary(business, end_date=end_date)
    data["business"] = business
    return render(request, "reports/cash_bank_summary.html", data)


@login_required
def day_book(request):
    """Day Book: all transactions for a single selected day. Columns: Date, Particulars, Voucher Type, Voucher No, Debit Amt, Credit Amt."""
    from ledger.models import Voucher, VoucherLine

    bid = get_active_business_id(request)
    if not bid:
        return redirect(reverse("org:select_business"))
    business = get_object_or_404(Business, id=bid)

    report_date = _parse_date(request.GET.get("date"))
    if not report_date:
        # Default to latest available posted voucher date for this business; fallback to today if none.
        last_date = (
            Voucher.objects.filter(business=business, is_posted=True)
            .order_by("-posting_date")
            .values_list("posting_date", flat=True)
            .first()
        )
        report_date = last_date or date.today()

    # Financial year in this system starts on 1-Apr each year.
    # Determine the start of the financial year that contains report_date.
    if report_date.month >= 4:
        fiscal_start_date = date(report_date.year, 4, 1)
    else:
        fiscal_start_date = date(report_date.year - 1, 4, 1)

    lines = (
        VoucherLine.objects.filter(
            voucher__business=business,
            voucher__is_posted=True,
            voucher__posting_date=report_date,
        )
        .select_related("voucher", "account")
        .order_by("voucher__posting_date", "voucher__id", "id")
    )

    transactions = []
    for line in lines:
        # Particulars: ledger name with Dr/Cr prefix (Tally-style)
        prefix = "Dr " if line.debit > 0 else "Cr "
        particulars = prefix + line.account.name
        transactions.append({
            "date": line.voucher.posting_date,
            "particulars": particulars,
            "vch_type": line.voucher.get_voucher_type_display(),
            "vch_no": line.voucher.number,
            "debit": line.debit,
            "credit": line.credit,
            "voucher_id": line.voucher_id,
        })

    total_dr = sum(t["debit"] for t in transactions)
    total_cr = sum(t["credit"] for t in transactions)

    return render(request, "reports/day_book.html", {
        "business": business,
        "report_date": report_date,
        "fiscal_start_date": fiscal_start_date,
        "transactions": transactions,
        "total_dr": total_dr,
        "total_cr": total_cr,
    })
