from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.db import IntegrityError
from django.db.models import Sum
from django.core.exceptions import ValidationError

from .forms import (
    StockGroupForm, StockItemForm, UnitOfMeasureForm, StandardRateForm, get_standard_rate_formset,
    GodownForm, PurchaseVoucherForm, SalesVoucherForm, StockJournalForm, purchase_row_formset,
)
from .models import StockGroup, StockMovement, Item, UnitOfMeasure, StandardRate, Godown, StockLedgerEntry


def _get_business_or_redirect(request):
    """Return (business, None) or (None, redirect_response)."""
    bid = request.session.get("current_business_id")
    if not bid:
        return None, HttpResponseRedirect(reverse("org:select_business"))
    from org.models import Business
    return get_object_or_404(Business, id=bid), None


@login_required
def balance_view(request):
    business_id = request.session.get("current_business_id")
    mode = request.session.get("current_mode", "BUSINESS")

    movements = (
        StockMovement.objects
        .filter(business_id=business_id, mode=mode)
        .values("item_id")
        .annotate(qty=Sum("qty_delta"))
    )
    qty_map = {m["item_id"]: m["qty"] for m in movements}
    items = Item.objects.filter(business_id=business_id).order_by("sku")
    rows = [(i, qty_map.get(i.id, 0) or 0) for i in items]

    return render(request, "inventory/balance.html", {"rows": rows})


@login_required
def gateway(request):
    """Inventory gateway: Stock Groups, Stock Items, Voucher Types, Units of Measure."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    return render(request, "inventory/gateway.html", {"business": business})


@login_required
def stock_groups_gateway(request):
    """Stock Groups sub-gateway: Single (Create, Display, Alter), Multiple (Create, Display, Alter)."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    return render(request, "inventory/stock_groups_gateway.html", {"business": business})


@require_http_methods(["GET", "POST"])
@login_required
def stock_group_create(request):
    """Single Stock Group creation (form like screenshot)."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = StockGroupForm(request.POST or None, business=business)
    if not request.POST:
        form.fields["parent"].initial = None  # Primary
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Stock group created.")
            return redirect("inventory:stock_groups_display")
        except IntegrityError:
            messages.error(
                request,
                "A stock group with this name already exists for this business.",
            )
        except ValidationError as e:
            messages.error(request, str(e))
    elif request.method == "POST":
        messages.error(request, "Could not save stock group. Please fix the errors below.")
    return render(request, "inventory/stock_group_form.html", {
        "business": business,
        "form": form,
        "title": "Stock Group Creation",
    })


@login_required
def stock_groups_display(request):
    """Display list of stock groups."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    groups = StockGroup.objects.filter(business=business).order_by("name")
    return render(request, "inventory/stock_groups_display.html", {
        "business": business,
        "groups": groups,
    })


@require_http_methods(["GET", "POST"])
@login_required
def stock_group_alter(request, pk: int):
    """Alter an existing stock group."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    group = get_object_or_404(StockGroup, pk=pk, business=business)
    form = StockGroupForm(request.POST or None, instance=group, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Stock group updated.")
            return redirect("inventory:stock_groups_display")
        except IntegrityError:
            messages.error(
                request,
                "A stock group with this name already exists for this business.",
            )
        except ValidationError as e:
            messages.error(request, str(e))
    elif request.method == "POST":
        messages.error(request, "Could not save stock group. Please fix the errors below.")
    return render(request, "inventory/stock_group_form.html", {
        "business": business,
        "form": form,
        "title": "Stock Group Alteration",
    })


# --- Stock Items (same pattern as Stock Groups) ---


@login_required
def stock_items_gateway(request):
    """Stock Items sub-gateway: Create, Display, Alter."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    return render(request, "inventory/stock_items_gateway.html", {"business": business})


@require_http_methods(["GET", "POST"])
@login_required
def stock_item_create(request):
    """Create a new stock item."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = StockItemForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Stock item created.")
            return redirect("inventory:standard_rates", pk=obj.pk)
        except IntegrityError:
            messages.error(
                request,
                "A stock item with this SKU already exists for this business.",
            )
        except ValidationError as e:
            messages.error(request, str(e))
    elif request.method == "POST":
        messages.error(request, "Could not save stock item. Please fix the errors below.")
    return render(request, "inventory/stock_item_form.html", {
        "business": business,
        "form": form,
        "title": "Stock Item Creation",
    })


@login_required
def stock_items_display(request):
    """Display list of stock items."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    items = Item.objects.filter(business=business).order_by("sku")
    return render(request, "inventory/stock_items_display.html", {
        "business": business,
        "items": items,
    })


@require_http_methods(["GET", "POST"])
@login_required
def stock_item_alter(request, pk: int):
    """Alter an existing stock item."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(Item, pk=pk, business=business)
    form = StockItemForm(request.POST or None, instance=item, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Stock item updated.")
            return redirect("inventory:standard_rates", pk=obj.pk)
        except IntegrityError:
            messages.error(
                request,
                "A stock item with this SKU already exists for this business.",
            )
        except ValidationError as e:
            messages.error(request, str(e))
    elif request.method == "POST":
        messages.error(request, "Could not save stock item. Please fix the errors below.")
    return render(request, "inventory/stock_item_form.html", {
        "business": business,
        "form": form,
        "title": "Stock Item Alteration",
    })


@require_http_methods(["GET", "POST"])
@login_required
def standard_rates(request, pk: int):
    """Standard Rates window for a stock item: Standard Cost and Standard Selling Price tables."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(Item, pk=pk, business=business)
    unit_symbol = str(item.unit) if item.unit else "—"

    CostFormSet = get_standard_rate_formset("COST")
    SellingFormSet = get_standard_rate_formset("SELLING")

    cost_queryset = StandardRate.objects.filter(item=item, rate_type="COST").order_by("-applicable_from")
    selling_queryset = StandardRate.objects.filter(item=item, rate_type="SELLING").order_by("-applicable_from")

    cost_formset = CostFormSet(
        request.POST or None,
        queryset=cost_queryset,
        prefix="cost",
    )
    selling_formset = SellingFormSet(
        request.POST or None,
        queryset=selling_queryset,
        prefix="selling",
    )

    if request.method == "POST":
        if cost_formset.is_valid() and selling_formset.is_valid():
            for form in cost_formset:
                if form.cleaned_data.get("DELETE") and form.instance.pk:
                    form.instance.delete()
                elif form.cleaned_data and not form.cleaned_data.get("DELETE") and form.cleaned_data.get("applicable_from") and form.cleaned_data.get("rate") is not None:
                    obj = form.save(commit=False)
                    obj.item = item
                    obj.rate_type = "COST"
                    obj.save()
            for form in selling_formset:
                if form.cleaned_data.get("DELETE") and form.instance.pk:
                    form.instance.delete()
                elif form.cleaned_data and not form.cleaned_data.get("DELETE") and form.cleaned_data.get("applicable_from") and form.cleaned_data.get("rate") is not None:
                    obj = form.save(commit=False)
                    obj.item = item
                    obj.rate_type = "SELLING"
                    obj.save()
            messages.success(request, "Standard rates updated.")
            return redirect("inventory:standard_rates", pk=item.pk)
        else:
            messages.error(request, "Please fix the errors below.")

    return render(request, "inventory/standard_rates.html", {
        "business": business,
        "item": item,
        "unit_symbol": unit_symbol,
        "cost_formset": cost_formset,
        "selling_formset": selling_formset,
    })


# --- Units of Measure (same pattern as Stock Groups) ---


@login_required
def units_gateway(request):
    """Units of Measure sub-gateway: Create, Display, Alter."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    return render(request, "inventory/units_gateway.html", {"business": business})


@require_http_methods(["GET", "POST"])
@login_required
def unit_create(request):
    """Create a new unit of measure."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = UnitOfMeasureForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Unit of measure created.")
            return redirect("inventory:units_display")
        except IntegrityError:
            messages.error(
                request,
                "A unit with this symbol already exists for this business.",
            )
        except ValidationError as e:
            messages.error(request, str(e))
    elif request.method == "POST":
        messages.error(request, "Could not save unit. Please fix the errors below.")
    return render(request, "inventory/unit_form.html", {
        "business": business,
        "form": form,
        "title": "Unit Creation (Secondary)",
    })


@login_required
def units_display(request):
    """Display list of units of measure."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    units = UnitOfMeasure.objects.filter(business=business).order_by("symbol")
    return render(request, "inventory/units_display.html", {
        "business": business,
        "units": units,
    })


@require_http_methods(["GET", "POST"])
@login_required
def unit_alter(request, pk: int):
    """Alter an existing unit of measure."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    unit = get_object_or_404(UnitOfMeasure, pk=pk, business=business)
    form = UnitOfMeasureForm(request.POST or None, instance=unit, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Unit updated.")
            return redirect("inventory:units_display")
        except IntegrityError:
            messages.error(
                request,
                "A unit with this symbol already exists for this business.",
            )
        except ValidationError as e:
            messages.error(request, str(e))
    elif request.method == "POST":
        messages.error(request, "Could not save unit. Please fix the errors below.")
    return render(request, "inventory/unit_form.html", {
        "business": business,
        "form": form,
        "title": "Unit Alteration",
    })


# --- Tally-style: Items (alias URLs), Warehouses, Stock Summary, Vouchers ---


def _stock_balance(business_id, item_id, godown_id=None):
    """Current stock = sum(qty_in) - sum(qty_out) for posted entries. Decimal."""
    qs = StockLedgerEntry.objects.filter(
        business_id=business_id, item_id=item_id, is_posted=True
    )
    if godown_id is not None:
        qs = qs.filter(godown_id=godown_id)
    agg = qs.aggregate(sin=Sum("qty_in"), sout=Sum("qty_out"))
    return (agg["sin"] or Decimal("0")) - (agg["sout"] or Decimal("0"))


@login_required
def items_list(request):
    """List items (Tally-style gateway URL)."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    items = Item.objects.filter(business=business).order_by("sku")
    return render(request, "inventory/items_list.html", {"business": business, "items": items})


@require_http_methods(["GET", "POST"])
@login_required
def item_create(request):
    """Create item (Tally-style gateway URL)."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = StockItemForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Item created.")
            return redirect("inventory:items_list")
        except IntegrityError:
            messages.error(request, "An item with this name already exists for this business.")
        except ValidationError as e:
            messages.error(request, str(e))
    elif request.method == "POST":
        messages.error(request, "Could not save item. Please fix the errors below.")
    return render(request, "inventory/item_form.html", {
        "business": business,
        "form": form,
        "title": "New Item",
    })


@require_http_methods(["GET", "POST"])
@login_required
def item_edit(request, pk: int):
    """Edit item (Tally-style gateway URL)."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(Item, pk=pk, business=business)
    form = StockItemForm(request.POST or None, instance=item, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Item updated.")
            return redirect("inventory:items_list")
        except IntegrityError:
            messages.error(request, "An item with this name already exists for this business.")
        except ValidationError as e:
            messages.error(request, str(e))
    elif request.method == "POST":
        messages.error(request, "Could not save item. Please fix the errors below.")
    return render(request, "inventory/item_form.html", {
        "business": business,
        "form": form,
        "title": "Edit Item",
    })


@login_required
def godowns_list(request):
    """List godowns (Tally: Godowns master)."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    godowns = Godown.objects.filter(business=business).order_by("name")
    return render(request, "inventory/godowns_list.html", {
        "business": business,
        "godowns": godowns,
    })


@require_http_methods(["GET", "POST"])
@login_required
def godown_create(request):
    """Create godown."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = GodownForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Godown created.")
            return redirect("inventory:godowns_list")
        except IntegrityError:
            messages.error(request, "A godown with this name already exists for this business.")
    elif request.method == "POST":
        messages.error(request, "Could not save godown. Please fix the errors below.")
    return render(request, "inventory/godown_form.html", {
        "business": business,
        "form": form,
        "title": "Create Godown",
    })


@require_http_methods(["GET", "POST"])
@login_required
def godown_edit(request, pk: int):
    """Alter godown."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    godown = get_object_or_404(Godown, pk=pk, business=business)
    form = GodownForm(request.POST or None, instance=godown, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.business = business
            obj.save()
            messages.success(request, "Godown updated.")
            return redirect("inventory:godowns_list")
        except IntegrityError:
            messages.error(request, "A godown with this name already exists for this business.")
    elif request.method == "POST":
        messages.error(request, "Could not save godown. Please fix the errors below.")
    return render(request, "inventory/godown_form.html", {
        "business": business,
        "form": form,
        "title": "Alter Godown",
    })


@login_required
def stock_summary(request):
    """Stock Summary report (Tally): per-item Qty In, Qty Out, Closing Qty. Posted entries only."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    godown_id = request.GET.get("godown")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    qs = StockLedgerEntry.objects.filter(business=business, is_posted=True)
    if godown_id:
        qs = qs.filter(godown_id=godown_id)
    if date_from:
        qs = qs.filter(posting_date__gte=date_from)
    if date_to:
        qs = qs.filter(posting_date__lte=date_to)

    rows = (
        qs.values("item_id", "item__sku")
        .annotate(total_in=Sum("qty_in"), total_out=Sum("qty_out"))
        .order_by("item__sku")
    )
    purchase_rates = _item_standard_cost_rates(business)  # item_id -> rate (str), standard COST = purchase rate
    summary_rows = []
    for r in rows:
        total_in = r["total_in"] or Decimal("0")
        total_out = r["total_out"] or Decimal("0")
        balance = total_in - total_out
        rate_str = purchase_rates.get(str(r["item_id"]), "0")
        purchase_rate = Decimal(rate_str) if rate_str else Decimal("0")
        closing_value = (balance * purchase_rate).quantize(Decimal("0.01"))
        summary_rows.append({
            "item_id": r["item_id"],
            "item_sku": r["item__sku"],
            "qty_in": total_in,
            "qty_out": total_out,
            "balance": balance,
            "closing_stock_value": closing_value,
        })

    godowns = Godown.objects.filter(business=business).order_by("name")
    return render(request, "inventory/stock_summary.html", {
        "business": business,
        "summary_rows": summary_rows,
        "godowns": godowns,
        "selected_godown_id": godown_id,
        "date_from": date_from or "",
        "date_to": date_to or "",
    })


def _entry_amount(qty_in, qty_out, rate):
    """amount = abs(qty_in - qty_out) * rate, rounded to 2 decimals."""
    qty = abs((qty_in or Decimal("0")) - (qty_out or Decimal("0")))
    return (qty * rate).quantize(Decimal("0.01"))


def _next_voucher_number(business):
    from ledger.models import Voucher
    n = Voucher.objects.filter(business=business).count() + 1
    return str(n)


def _item_standard_cost_rates(business):
    """Return dict item_id -> rate (str) for latest standard COST rate per item. For JS rate auto-fill."""
    from django.db.models import OuterRef, Subquery
    latest = StandardRate.objects.filter(
        item=OuterRef("pk"), rate_type="COST"
    ).order_by("-applicable_from")
    items_with_rate = Item.objects.filter(
        business=business, is_stock_item=True
    ).annotate(
        latest_rate=Subquery(latest.values("rate")[:1])
    ).filter(latest_rate__isnull=False)
    return {str(i.pk): str(i.latest_rate) for i in items_with_rate}


def _item_standard_selling_rates(business):
    """Return dict item_id -> rate (str) for latest standard SELLING rate per item. For JS rate auto-fill on sales."""
    from django.db.models import OuterRef, Subquery
    latest = StandardRate.objects.filter(
        item=OuterRef("pk"), rate_type="SELLING"
    ).order_by("-applicable_from")
    items_with_rate = Item.objects.filter(
        business=business, is_stock_item=True
    ).annotate(
        latest_rate=Subquery(latest.values("rate")[:1])
    ).filter(latest_rate__isnull=False)
    return {str(i.pk): str(i.latest_rate) for i in items_with_rate}


def _purchase_totals_from_formset(row_formset):
    """Compute total_qty and total_amount from formset (cleaned_data or raw POST)."""
    total_qty = Decimal("0")
    total_amount = Decimal("0")
    prefix = getattr(row_formset, "prefix", "form")
    if not prefix:
        prefix = "form"
    for i, form in enumerate(row_formset.forms):
        cd = getattr(form, "cleaned_data", None)
        if cd and cd.get("item") and cd.get("qty") and cd.get("qty") > 0:
            q, r = cd["qty"], cd["rate"]
            total_qty += q
            total_amount += (q * r).quantize(Decimal("0.01"))
        elif form.data:
            try:
                q = form.data.get(f"{prefix}-{i}-qty")
                r = form.data.get(f"{prefix}-{i}-rate")
                if q and r:
                    qd = Decimal(q)
                    rd = Decimal(r)
                    if qd > 0:
                        total_qty += qd
                        total_amount += (qd * rd).quantize(Decimal("0.01"))
            except (TypeError, ValueError, InvalidOperation):
                pass
    return total_qty, total_amount


@require_http_methods(["GET", "POST"])
@login_required
def purchase_voucher_create(request):
    """
    Inventory Voucher — Purchase. Creates both:
    1) Stock movements (StockLedgerEntry)
    2) Accounting voucher (ledger.Voucher + VoucherLine)
    """
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    from ledger.models import Voucher, VoucherLine, VoucherType
    from mode_engine.models import ModeChoices

    form = PurchaseVoucherForm(request.POST or None, business=business)
    row_formset = purchase_row_formset(business, data=request.POST if request.method == "POST" else None)

    total_qty = total_amount = None
    if request.method == "POST":
        total_qty, total_amount = _purchase_totals_from_formset(row_formset)
        if total_qty is not None and total_qty > 0:
            total_amount = total_amount or Decimal("0")

    if request.method == "POST" and form.is_valid() and row_formset.is_valid():
        cd = form.cleaned_data
        rows = [r for r in row_formset.cleaned_data if r.get("item") and r.get("qty") and r.get("qty") > 0]
        if not rows:
            form.add_error(None, "Add at least one item row with qty > 0.")
        else:
            total = sum((r["qty"] * r["rate"]).quantize(Decimal("0.01")) for r in rows)
            narration = cd.get("narration") or ""
            if cd.get("supplier_invoice_no"):
                narration = (f"Supplier invoice no.: {cd['supplier_invoice_no']}. " + narration).strip()
            try:
                with transaction.atomic():
                    v = Voucher(
                        business=business,
                        number=_next_voucher_number(business),
                        voucher_type=VoucherType.PURCHASE,
                        mode=ModeChoices.BUSINESS,
                        posting_date=cd["posting_date"],
                        narration=narration,
                        is_posted=False,
                    )
                    v.save()
                    VoucherLine.objects.create(voucher=v, account=cd["purchase_ledger"], debit=total, credit=Decimal("0"))
                    VoucherLine.objects.create(voucher=v, account=cd["party"], debit=Decimal("0"), credit=total)
                    for r in rows:
                        qty, rate = r["qty"], r["rate"]
                        amount = _entry_amount(qty, Decimal("0"), rate)
                        StockLedgerEntry.objects.create(
                            business=business,
                            posting_date=cd["posting_date"],
                            item=r["item"],
                            godown=cd["godown"],
                            qty_in=qty,
                            qty_out=Decimal("0"),
                            rate=rate,
                            amount=amount,
                            voucher_type="PURCHASE",
                            voucher_id=v.id,
                            is_posted=True,
                            narration=narration,
                        )
                    v.post(user=request.user)
                messages.success(request, "Purchase voucher posted.")
                return redirect("inventory:stock_summary")
            except Exception as e:
                messages.error(request, f"Could not save: {e}")

    voucher_number = _next_voucher_number(business) if request.method != "POST" else None
    if total_qty is None and request.method == "POST":
        total_qty, total_amount = _purchase_totals_from_formset(row_formset)
    # Latest standard cost per item (for rate auto-fill when item is selected)
    import json
    item_rates = _item_standard_cost_rates(business)
    return render(request, "inventory/vouchers/purchase.html", {
        "business": business,
        "form": form,
        "row_formset": row_formset,
        "voucher_number": voucher_number,
        "total_qty": total_qty,
        "total_amount": total_amount,
        "item_rates_json": json.dumps(item_rates),
    })


@require_http_methods(["GET", "POST"])
@login_required
def sales_voucher(request):
    """Sales (with items): Party Dr, Sales Cr; stock out. Validates no negative stock."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    from ledger.models import Voucher, VoucherLine, VoucherType
    from mode_engine.models import ModeChoices

    form = SalesVoucherForm(request.POST or None, business=business)
    row_formset = purchase_row_formset(business, data=request.POST if request.method == "POST" else None)  # same row shape

    if request.method == "POST" and form.is_valid() and row_formset.is_valid():
        cd = form.cleaned_data
        rows = [r for r in row_formset.cleaned_data if r.get("item") and r.get("qty") and r.get("qty") > 0]
        if not rows:
            form.add_error(None, "Add at least one item row with qty > 0.")
        else:
            total = sum((r["qty"] * r["rate"]).quantize(Decimal("0.01")) for r in rows)
            # Validate stock in godown for each row
            errors = []
            for r in rows:
                bal = _stock_balance(business.id, r["item"].id, cd["godown"].id)
                if bal < r["qty"]:
                    errors.append(f"{r['item'].sku}: insufficient stock (have {bal}, need {r['qty']})")
            if errors:
                form.add_error(None, " ".join(errors))
            else:
                try:
                    with transaction.atomic():
                        v = Voucher(
                            business=business,
                            number=_next_voucher_number(business),
                            voucher_type=VoucherType.SALES,
                            mode=ModeChoices.BUSINESS,
                            posting_date=cd["posting_date"],
                            narration=cd.get("narration") or "",
                            is_posted=False,
                        )
                        v.save()
                        VoucherLine.objects.create(voucher=v, account=cd["party"], debit=total, credit=Decimal("0"))
                        VoucherLine.objects.create(voucher=v, account=cd["sales_ledger"], debit=Decimal("0"), credit=total)
                        for r in rows:
                            qty, rate = r["qty"], r["rate"]
                            amount = _entry_amount(Decimal("0"), qty, rate)
                            StockLedgerEntry.objects.create(
                                business=business,
                                posting_date=cd["posting_date"],
                                item=r["item"],
                                godown=cd["godown"],
                                qty_in=Decimal("0"),
                                qty_out=qty,
                                rate=rate,
                                amount=amount,
                                voucher_type="SALES",
                                voucher_id=v.id,
                                is_posted=True,
                                narration=cd.get("narration") or "",
                            )
                        v.post(user=request.user)
                    messages.success(request, "Sales voucher posted.")
                    return redirect("inventory:stock_summary")
                except Exception as e:
                    messages.error(request, f"Could not save: {e}")
    total_qty = total_amount = None
    if request.method == "POST":
        total_qty, total_amount = _purchase_totals_from_formset(row_formset)
    import json
    item_rates = _item_standard_selling_rates(business)
    return render(request, "inventory/voucher_sales.html", {
        "business": business,
        "form": form,
        "row_formset": row_formset,
        "total_qty": total_qty,
        "total_amount": total_amount,
        "item_rates_json": json.dumps(item_rates),
    })


@require_http_methods(["GET", "POST"])
@login_required
def stock_journal(request):
    """Stock Journal: transfer From Godown to To Godown. Two entries atomically."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = StockJournalForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        item = cd["item"]
        from_g = cd["from_godown"]
        to_g = cd["to_godown"]
        qty = cd["qty"]
        rate = cd.get("rate") or Decimal("0")
        balance = _stock_balance(business.id, item.id, from_g.id)
        if balance < qty:
            form.add_error("qty", f"Insufficient stock in source godown. Current balance is {balance}.")
        else:
            amount = _entry_amount(Decimal("0"), qty, rate)
            try:
                with transaction.atomic():
                    StockLedgerEntry.objects.create(
                        business=business,
                        posting_date=cd["posting_date"],
                        item=item,
                        godown=from_g,
                        qty_in=Decimal("0"),
                        qty_out=qty,
                        rate=rate,
                        amount=amount,
                        voucher_type="STOCK_JOURNAL",
                        is_posted=True,
                        narration=cd.get("narration") or "",
                    )
                    StockLedgerEntry.objects.create(
                        business=business,
                        posting_date=cd["posting_date"],
                        item=item,
                        godown=to_g,
                        qty_in=qty,
                        qty_out=Decimal("0"),
                        rate=rate,
                        amount=amount,
                        voucher_type="STOCK_JOURNAL",
                        is_posted=True,
                        narration=cd.get("narration") or "",
                    )
                messages.success(request, "Stock Journal posted.")
                return redirect("inventory:stock_summary")
            except Exception:
                messages.error(request, "Could not save. Please try again.")
    return render(request, "inventory/voucher_stock_journal.html", {"business": business, "form": form})
