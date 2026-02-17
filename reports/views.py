from decimal import Decimal
from datetime import date
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ledger.services.balance_sheet import compute_balance_sheet
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
    return render(request, "reports/home.html")


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
    """Balance Sheet: Liabilities (left) and Assets (right). Profit & Loss A/c row shows gross profit from P&L."""
    bid = get_active_business_id(request)
    if not bid:
        return redirect(reverse("org:select_business"))
    business = get_object_or_404(Business, id=bid)
    end_date = _parse_date(request.GET.get("end_date"))
    data = compute_balance_sheet(business, end_date=end_date)
    data["business"] = business
    data["end_date"] = end_date
    return render(request, "reports/balance_sheet.html", data)
