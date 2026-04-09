from decimal import Decimal, InvalidOperation
from collections import defaultdict
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from config.financial_year import financial_year_start
from django.views.decorators.http import require_http_methods
from django.db import IntegrityError
from django.db.models import Sum, Q
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError

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


def _standard_rate_formsets(request, item):
    CostFormSet = get_standard_rate_formset("COST")
    SellingFormSet = get_standard_rate_formset("SELLING")
    cost_queryset = StandardRate.objects.filter(item=item, rate_type="COST").order_by("-applicable_from")
    selling_queryset = StandardRate.objects.filter(item=item, rate_type="SELLING").order_by("-applicable_from")
    return (
        CostFormSet(request.POST or None, queryset=cost_queryset, prefix="cost"),
        SellingFormSet(request.POST or None, queryset=selling_queryset, prefix="selling"),
    )


def _persist_standard_rates(item, cost_formset, selling_formset):
    for form in cost_formset:
        if form.cleaned_data.get("DELETE") and form.instance.pk:
            form.instance.delete()
        elif (
            form.cleaned_data
            and not form.cleaned_data.get("DELETE")
            and form.cleaned_data.get("applicable_from")
            and form.cleaned_data.get("rate") is not None
        ):
            obj = form.save(commit=False)
            obj.item = item
            obj.rate_type = "COST"
            obj.save()
    for form in selling_formset:
        if form.cleaned_data.get("DELETE") and form.instance.pk:
            form.instance.delete()
        elif (
            form.cleaned_data
            and not form.cleaned_data.get("DELETE")
            and form.cleaned_data.get("applicable_from")
            and form.cleaned_data.get("rate") is not None
        ):
            obj = form.save(commit=False)
            obj.item = item
            obj.rate_type = "SELLING"
            obj.save()


def _default_opening_godown(business):
    """Return a predictable godown for opening stock seeds, creating one if needed."""
    godown = Godown.objects.filter(business=business).order_by("id").first()
    if godown:
        return godown
    godown, _ = Godown.objects.get_or_create(business=business, name="Main Location")
    return godown


def _sync_opening_stock_seed(item, business):
    """
    Idempotently mirror Item opening balance into StockLedgerEntry (voucher_type=OPENING).
    - qty_in = opening_qty, qty_out = 0
    - posting_date = current FY start
    - if opening qty is empty/zero, remove seed rows
    """
    qty = item.opening_qty or Decimal("0")
    seed_qs = StockLedgerEntry.objects.filter(
        business=business,
        item=item,
        voucher_type="OPENING",
        voucher_id__isnull=True,
        is_posted=True,
    )
    if qty <= 0:
        seed_qs.delete()
        return

    godown = _default_opening_godown(business)
    posting_date = financial_year_start(timezone.localdate())
    rate = item.opening_rate or Decimal("0")
    amount = item.opening_value
    if amount is None:
        amount = (qty * rate).quantize(Decimal("0.01"))
    narration = "Opening balance seed (auto)"

    seed_row = (
        seed_qs.filter(godown=godown)
        .order_by("id")
        .first()
    )
    if seed_row:
        seed_row.posting_date = posting_date
        seed_row.qty_in = qty
        seed_row.qty_out = Decimal("0")
        seed_row.rate = rate
        seed_row.amount = amount
        seed_row.narration = narration
        seed_row.save(
            update_fields=[
                "posting_date",
                "qty_in",
                "qty_out",
                "rate",
                "amount",
                "narration",
                "updated_at",
            ]
        )
    else:
        StockLedgerEntry.objects.create(
            business=business,
            posting_date=posting_date,
            item=item,
            godown=godown,
            qty_in=qty,
            qty_out=Decimal("0"),
            rate=rate,
            amount=amount,
            voucher_type="OPENING",
            voucher_id=None,
            is_posted=True,
            narration=narration,
        )

    # Keep exactly one seed for this item/business across godowns.
    seed_qs.exclude(pk=(seed_row.pk if seed_row else None)).delete()


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


@require_http_methods(["GET", "POST"])
@login_required
def stock_group_create(request):
    """Single Stock Group creation (form like screenshot)."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    group_type = (request.POST.get("group_type") or request.GET.get("type") or "any").strip().lower()
    if group_type not in {"main", "sub"}:
        group_type = "any"
    form = StockGroupForm(request.POST or None, business=business, group_type=group_type)
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
    if group_type == "main":
        title = "Stock Main Group Creation"
        under_hint = 'Only "Primary" is allowed here.'
    elif group_type == "sub":
        title = "Stock Sub Group Creation"
        under_hint = "Choose a main group as parent."
    else:
        title = "Stock Group Creation"
        under_hint = 'Select "Primary" for a top-level group.'
    return render(request, "inventory/stock_group_form.html", {
        "business": business,
        "form": form,
        "title": title,
        "group_type": group_type,
        "under_hint": under_hint,
    })


@login_required
def stock_groups_display(request):
    """Display list of stock groups."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    # Show groups in a hierarchical way: top (parent=None) -> sub-groups.
    groups = (
        StockGroup.objects.filter(business=business, parent__isnull=True)
        .prefetch_related("children")
        .order_by("name")
    )
    return render(request, "inventory/stock_groups_display.html", {
        "business": business,
        "groups": groups,
    })


@login_required
def stock_main_groups_display(request):
    """Display list of top-level stock groups with search."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    search_query = (request.GET.get("q") or "").strip()
    groups = StockGroup.objects.filter(business=business, parent__isnull=True)
    if search_query:
        groups = groups.filter(Q(name__icontains=search_query) | Q(alias__icontains=search_query))
    groups = groups.order_by("name")
    return render(request, "inventory/stock_main_groups_display.html", {
        "business": business,
        "groups": groups,
        "search_query": search_query,
    })


@login_required
def stock_sub_groups_display(request):
    """Display sub-groups grouped under main groups (collapsible tree) with search."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    search_query = (request.GET.get("q") or "").strip()
    parents = StockGroup.objects.filter(business=business, parent__isnull=True).prefetch_related("children").order_by("name")
    parent_rows = []
    for parent in parents:
        children_qs = parent.children.all().order_by("name")
        if search_query:
            children_qs = children_qs.filter(Q(name__icontains=search_query) | Q(alias__icontains=search_query))
        children = list(children_qs)
        if search_query and not children:
            continue
        parent_rows.append({"parent": parent, "children": children})
    return render(request, "inventory/stock_sub_groups_display.html", {
        "business": business,
        "parent_rows": parent_rows,
        "search_query": search_query,
    })


@require_http_methods(["GET"])
@login_required
def stock_group_display(request, pk: int):
    """Read-only stock group detail window."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    group = get_object_or_404(StockGroup, pk=pk, business=business)
    return render(request, "inventory/stock_group_display.html", {
        "business": business,
        "group": group,
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


@require_http_methods(["POST"])
@login_required
def stock_group_delete(request, pk: int):
    """Delete a stock group when not referenced by protected relations."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    group = get_object_or_404(StockGroup, pk=pk, business=business)
    try:
        group.delete()
        messages.success(request, "Stock group deleted.")
    except ProtectedError:
        messages.error(
            request,
            "Cannot delete this stock group because it is used by items or subgroups.",
        )
    return redirect("inventory:stock_groups_display")


# --- Stock Items (same pattern as Stock Groups) ---


@require_http_methods(["GET", "POST"])
@login_required
def stock_item_create(request):
    """Create a new stock item."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = StockItemForm(request.POST or None, business=business)
    CostFormSet = get_standard_rate_formset("COST")
    SellingFormSet = get_standard_rate_formset("SELLING")
    cost_formset = CostFormSet(request.POST or None, queryset=StandardRate.objects.none(), prefix="cost")
    selling_formset = SellingFormSet(request.POST or None, queryset=StandardRate.objects.none(), prefix="selling")

    if request.method == "POST":
        if form.is_valid() and cost_formset.is_valid() and selling_formset.is_valid():
            try:
                with transaction.atomic():
                    obj = form.save(commit=False)
                    obj.business = business
                    obj.save()
                    _sync_opening_stock_seed(obj, business)
                    _persist_standard_rates(obj, cost_formset, selling_formset)
                messages.success(request, "Stock item created.")
                return redirect("inventory:stock_item_display", pk=obj.pk)
            except IntegrityError:
                messages.error(
                    request,
                    "A stock item with this SKU already exists for this business.",
                )
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Could not save stock item. Please fix the errors below.")

    unit_symbol = "—"
    unit_id = request.POST.get("unit")
    if unit_id:
        unit = UnitOfMeasure.objects.filter(business=business, pk=unit_id).first()
        if unit:
            unit_symbol = str(unit)
    return render(request, "inventory/stock_item_form.html", {
        "business": business,
        "form": form,
        "cost_formset": cost_formset,
        "selling_formset": selling_formset,
        "unit_symbol": unit_symbol,
        "title": "Stock Item Creation",
    })


@login_required
def stock_items_display(request):
    """Display list of stock items."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    search_query = (request.GET.get("q") or "").strip()

    search_results = None
    # When searching, find items by code (sku), description/alias, or part number/name
    if search_query:
        search_results = (
            Item.objects.filter(business=business)
            .filter(
                Q(sku__icontains=search_query)
                | Q(alias__icontains=search_query)
                | Q(name__icontains=search_query)
            )
            .order_by("sku")
        )
        groups = ()
        ungrouped_items = ()
    else:
        # Show items grouped under their stock groups (top-level + sub-groups).
        groups = (
            StockGroup.objects.filter(business=business, parent__isnull=True)
            .prefetch_related("items", "children__items")
            .order_by("name")
        )
        # Items without any stock group (Primary)
        ungrouped_items = Item.objects.filter(business=business, stock_group__isnull=True).order_by("sku")
    return render(request, "inventory/stock_items_display.html", {
        "business": business,
        "groups": groups,
        "ungrouped_items": ungrouped_items,
        "search_query": search_query,
        "search_results": search_results,
    })


@require_http_methods(["GET"])
@login_required
def stock_item_display(request, pk: int):
    """Read-only stock item detail: master, opening balance, standard rates."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(Item, pk=pk, business=business)
    unit_symbol = str(item.unit) if item.unit else "—"
    cost_latest = (
        StandardRate.objects.filter(item=item, rate_type="COST").order_by("-applicable_from").first()
    )
    selling_latest = (
        StandardRate.objects.filter(item=item, rate_type="SELLING").order_by("-applicable_from").first()
    )
    return render(request, "inventory/stock_item_display.html", {
        "business": business,
        "item": item,
        "unit_symbol": unit_symbol,
        "cost_latest": cost_latest,
        "selling_latest": selling_latest,
    })


@require_http_methods(["GET", "POST"])
@login_required
def stock_item_alter(request, pk: int):
    """Alter stock item: master fields, opening balance, and standard rates."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(Item, pk=pk, business=business)
    cost_formset, selling_formset = _standard_rate_formsets(request, item)
    form = StockItemForm(request.POST or None, instance=item, business=business)
    if request.method == "POST":
        if form.is_valid() and cost_formset.is_valid() and selling_formset.is_valid():
            try:
                with transaction.atomic():
                    obj = form.save(commit=False)
                    obj.business = business
                    obj.save()
                    _sync_opening_stock_seed(obj, business)
                    _persist_standard_rates(obj, cost_formset, selling_formset)
                messages.success(request, "Stock item saved.")
                return redirect("inventory:stock_item_display", pk=obj.pk)
            except IntegrityError:
                messages.error(
                    request,
                    "A stock item with this SKU already exists for this business.",
                )
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Please fix the errors below.")
    unit_symbol = str(item.unit) if item.unit else "—"
    return render(request, "inventory/stock_item_alter.html", {
        "business": business,
        "form": form,
        "item": item,
        "unit_symbol": unit_symbol,
        "cost_formset": cost_formset,
        "selling_formset": selling_formset,
        "title": "Stock Item Alteration",
    })


@require_http_methods(["POST"])
@login_required
def stock_item_delete(request, pk: int):
    """Delete a stock item when not referenced by protected relations."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(Item, pk=pk, business=business)
    try:
        StockLedgerEntry.objects.filter(
            business=business,
            item=item,
            voucher_type="OPENING",
            voucher_id__isnull=True,
            is_posted=True,
        ).delete()
        item.delete()
        messages.success(request, "Stock item deleted.")
    except ProtectedError:
        messages.error(
            request,
            "Cannot delete this stock item because it is used in posted entries or other records.",
        )
    return redirect("inventory:stock_items_display")


@login_required
def standard_rates(request, pk: int):
    """Legacy URL: standard rates are edited on Stock Item Alteration; redirect to display."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    get_object_or_404(Item, pk=pk, business=business)
    return redirect("inventory:stock_item_display", pk=pk)


# --- Units of Measure (same pattern as Stock Groups) ---


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
    search_query = (request.GET.get("q") or "").strip()
    units = UnitOfMeasure.objects.filter(business=business)
    if search_query:
        units = units.filter(Q(symbol__icontains=search_query) | Q(formal_name__icontains=search_query))
    units = units.order_by("symbol")
    return render(request, "inventory/units_display.html", {
        "business": business,
        "units": units,
        "search_query": search_query,
    })


@require_http_methods(["GET"])
@login_required
def unit_display(request, pk: int):
    """Read-only unit detail window."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    unit = get_object_or_404(UnitOfMeasure, pk=pk, business=business)
    return render(request, "inventory/unit_display.html", {
        "business": business,
        "unit": unit,
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


@require_http_methods(["POST"])
@login_required
def unit_delete(request, pk: int):
    """Delete a unit of measure."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    unit = get_object_or_404(UnitOfMeasure, pk=pk, business=business)
    try:
        unit.delete()
        messages.success(request, "Unit deleted.")
    except ProtectedError:
        messages.error(
            request,
            "Cannot delete this unit because it is referenced by other records.",
        )
    return redirect("inventory:units_display")


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
            _sync_opening_stock_seed(obj, business)
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
            _sync_opening_stock_seed(obj, business)
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
    today = timezone.localdate()
    period_start = financial_year_start(today)
    period_end = today

    qs = StockLedgerEntry.objects.filter(business=business, is_posted=True)
    if godown_id:
        qs = qs.filter(godown_id=godown_id)
    qs = qs.filter(posting_date__gte=period_start, posting_date__lte=period_end)

    rows = (
        qs.values("item_id")
        .annotate(total_in=Sum("qty_in"), total_out=Sum("qty_out"))
        .order_by("item_id")
    )
    purchase_rates = _item_standard_cost_rates(business)  # item_id -> rate (str), standard COST = purchase rate
    item_ids = [r["item_id"] for r in rows]
    items_by_id = {
        i.id: i
        for i in Item.objects.filter(business=business, id__in=item_ids).select_related("stock_group__parent")
    }
    main_groups_map = {}

    def _get_or_create_main_group(key, name):
        if key not in main_groups_map:
            main_groups_map[key] = {
                "main_group_name": name,
                "closing_qty": Decimal("0"),
                "closing_stock_value": Decimal("0.00"),
                "sub_groups_map": {},
            }
        return main_groups_map[key]

    def _add_subgroup(main_group, subgroup_key, subgroup_id, name, qty, value):
        if subgroup_key not in main_group["sub_groups_map"]:
            main_group["sub_groups_map"][subgroup_key] = {
                "id": subgroup_id,
                "name": name,
                "closing_qty": Decimal("0"),
                "closing_stock_value": Decimal("0.00"),
            }
        main_group["sub_groups_map"][subgroup_key]["closing_qty"] += qty
        main_group["sub_groups_map"][subgroup_key]["closing_stock_value"] += value

    for r in rows:
        total_in = r["total_in"] or Decimal("0")
        total_out = r["total_out"] or Decimal("0")
        balance = total_in - total_out
        item = items_by_id.get(r["item_id"])
        rate_str = purchase_rates.get(str(r["item_id"]))
        if rate_str is not None:
            purchase_rate = Decimal(rate_str)
        else:
            # Fallback: if no standard COST rate, use opening balance rate from item master.
            purchase_rate = (item.opening_rate if item and item.opening_rate is not None else Decimal("0"))
        closing_value = (balance * purchase_rate).quantize(Decimal("0.01"))
        stock_group = item.stock_group if item else None

        if stock_group is None:
            main_group = _get_or_create_main_group(("primary", 0), "Primary (No Group)")
            _add_subgroup(main_group, ("direct", 0), None, "(Direct items)", balance, closing_value)
        elif stock_group.parent_id is None:
            main_group = _get_or_create_main_group(("main", stock_group.id), stock_group.name)
            _add_subgroup(main_group, ("direct", stock_group.id), None, "(Direct items)", balance, closing_value)
        else:
            main_group = _get_or_create_main_group(("main", stock_group.parent_id), stock_group.parent.name)
            _add_subgroup(main_group, ("sub", stock_group.id), stock_group.id, stock_group.name, balance, closing_value)

        main_group["closing_qty"] += balance
        main_group["closing_stock_value"] += closing_value

    summary_rows = []
    for row in sorted(main_groups_map.values(), key=lambda x: x["main_group_name"].lower()):
        sub_groups = sorted(row["sub_groups_map"].values(), key=lambda x: x["name"].lower())
        row["sub_groups"] = sub_groups
        del row["sub_groups_map"]
        summary_rows.append(row)

    godowns = Godown.objects.filter(business=business).order_by("name")
    return render(request, "inventory/stock_summary.html", {
        "business": business,
        "summary_rows": summary_rows,
        "godowns": godowns,
        "selected_godown_id": godown_id,
        "period_start": period_start,
        "period_end": period_end,
    })


@require_http_methods(["GET"])
@login_required
def stock_summary_sub_group(request, pk: int):
    """Stock Summary detail for a single sub group (item-wise), no rate column."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response

    subgroup = get_object_or_404(
        StockGroup.objects.select_related("parent"),
        pk=pk,
        business=business,
        parent__isnull=False,
    )
    godown_id = request.GET.get("godown")
    today = timezone.localdate()
    period_start = financial_year_start(today)
    period_end = today

    qs = StockLedgerEntry.objects.filter(
        business=business,
        is_posted=True,
        posting_date__gte=period_start,
        posting_date__lte=period_end,
        item__stock_group=subgroup,
    )
    if godown_id:
        qs = qs.filter(godown_id=godown_id)

    rows = (
        qs.values("item_id", "item__sku")
        .annotate(total_in=Sum("qty_in"), total_out=Sum("qty_out"))
        .order_by("item__sku")
    )
    purchase_rates = _item_standard_cost_rates(business)
    items_by_id = {
        i.id: i
        for i in Item.objects.filter(business=business, stock_group=subgroup).only("id", "opening_rate")
    }

    detail_rows = []
    for r in rows:
        total_in = r["total_in"] or Decimal("0")
        total_out = r["total_out"] or Decimal("0")
        balance = total_in - total_out
        item = items_by_id.get(r["item_id"])
        rate_str = purchase_rates.get(str(r["item_id"]))
        if rate_str is not None:
            purchase_rate = Decimal(rate_str)
        else:
            purchase_rate = (item.opening_rate if item and item.opening_rate is not None else Decimal("0"))
        closing_value = (balance * purchase_rate).quantize(Decimal("0.01"))
        detail_rows.append({
            "item_sku": r["item__sku"],
            "qty_in": total_in,
            "qty_out": total_out,
            "closing_qty": balance,
            "closing_stock_value": closing_value,
        })

    return render(request, "inventory/stock_summary_sub_group.html", {
        "business": business,
        "subgroup": subgroup,
        "rows": detail_rows,
        "period_start": period_start,
        "period_end": period_end,
        "selected_godown_id": godown_id or "",
    })


def _stock_analysis_item_totals(business, period_start, period_end, godown_id=None, main_group=None, sub_group=None):
    qs = StockLedgerEntry.objects.filter(
        business=business,
        is_posted=True,
        posting_date__gte=period_start,
        posting_date__lte=period_end,
    ).select_related("item__stock_group__parent")
    if godown_id:
        qs = qs.filter(godown_id=godown_id)
    if sub_group is not None:
        qs = qs.filter(item__stock_group=sub_group)
    elif main_group is not None:
        qs = qs.filter(Q(item__stock_group=main_group) | Q(item__stock_group__parent=main_group))

    by_item = {}
    for e in qs:
        key = e.item_id
        if key not in by_item:
            by_item[key] = {
                "item_id": key,
                "item_sku": e.item.sku,
                "stock_group": e.item.stock_group,
                "latest_date": None,
                "inward_qty": Decimal("0"),
                "inward_value": Decimal("0"),
                "outward_qty": Decimal("0"),
                "outward_value": Decimal("0"),
            }
        row = by_item[key]
        if row["latest_date"] is None or e.posting_date > row["latest_date"]:
            row["latest_date"] = e.posting_date
        if e.qty_in and e.qty_in > 0:
            row["inward_qty"] += e.qty_in
            row["inward_value"] += (e.amount or Decimal("0"))
        if e.qty_out and e.qty_out > 0:
            row["outward_qty"] += e.qty_out
            row["outward_value"] += (e.amount or Decimal("0"))

    rows = list(by_item.values())
    for row in rows:
        row["inward_rate"] = (row["inward_value"] / row["inward_qty"]).quantize(Decimal("0.01")) if row["inward_qty"] else Decimal("0.00")
        row["outward_rate"] = (row["outward_value"] / row["outward_qty"]).quantize(Decimal("0.01")) if row["outward_qty"] else Decimal("0.00")
    return rows


def _movement_label_maps(voucher_ids):
    """
    Build voucher-wise display labels from accounting lines.
    - Purchase inward label: first credit line account (party/supplier)
    - Sales outward label: first debit line account (party/buyer)
    """
    if not voucher_ids:
        return {}, {}
    from ledger.models import VoucherLine

    purchase_labels = {}
    sales_labels = {}
    lines = VoucherLine.objects.filter(voucher_id__in=voucher_ids).select_related("account")
    for line in lines:
        if line.voucher_id not in purchase_labels and line.credit and line.credit > 0:
            purchase_labels[line.voucher_id] = line.account.name
        if line.voucher_id not in sales_labels and line.debit and line.debit > 0:
            sales_labels[line.voucher_id] = line.account.name
    return purchase_labels, sales_labels


@login_required
def stock_analysis(request):
    """Movement analysis by main groups."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    godown_id = request.GET.get("godown")
    period_start = financial_year_start(timezone.localdate())
    period_end = timezone.localdate()

    item_rows = _stock_analysis_item_totals(business, period_start, period_end, godown_id=godown_id)
    main_groups = {}
    for r in item_rows:
        sg = r["stock_group"]
        if sg is None:
            key = ("primary", 0)
            name = "Primary (No Group)"
            group_id = None
        elif sg.parent_id is None:
            key = ("main", sg.id)
            name = sg.name
            group_id = sg.id
        else:
            key = ("main", sg.parent_id)
            name = sg.parent.name
            group_id = sg.parent_id
        if key not in main_groups:
            main_groups[key] = {
                "id": group_id,
                "name": name,
                "inward_qty": Decimal("0"),
                "inward_value": Decimal("0"),
                "outward_qty": Decimal("0"),
                "outward_value": Decimal("0"),
            }
        g = main_groups[key]
        g["inward_qty"] += r["inward_qty"]
        g["inward_value"] += r["inward_value"]
        g["outward_qty"] += r["outward_qty"]
        g["outward_value"] += r["outward_value"]

    rows = sorted(main_groups.values(), key=lambda x: x["name"].lower())
    for row in rows:
        row["inward_rate"] = (row["inward_value"] / row["inward_qty"]).quantize(Decimal("0.01")) if row["inward_qty"] else Decimal("0.00")
        row["outward_rate"] = (row["outward_value"] / row["outward_qty"]).quantize(Decimal("0.01")) if row["outward_qty"] else Decimal("0.00")

    totals = {
        "inward_qty": sum((r["inward_qty"] for r in rows), Decimal("0")),
        "inward_value": sum((r["inward_value"] for r in rows), Decimal("0")),
        "outward_qty": sum((r["outward_qty"] for r in rows), Decimal("0")),
        "outward_value": sum((r["outward_value"] for r in rows), Decimal("0")),
    }
    totals["inward_rate"] = (totals["inward_value"] / totals["inward_qty"]).quantize(Decimal("0.01")) if totals["inward_qty"] else Decimal("0.00")
    totals["outward_rate"] = (totals["outward_value"] / totals["outward_qty"]).quantize(Decimal("0.01")) if totals["outward_qty"] else Decimal("0.00")

    return render(request, "inventory/stock_analysis_main.html", {
        "business": business,
        "rows": rows,
        "totals": totals,
        "period_start": period_start,
        "period_end": period_end,
        "selected_godown_id": godown_id or "",
    })


@login_required
def stock_analysis_sub_groups(request, pk: int):
    """Movement analysis by sub groups within a main group."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    main_group = get_object_or_404(StockGroup, pk=pk, business=business, parent__isnull=True)
    godown_id = request.GET.get("godown")
    period_start = financial_year_start(timezone.localdate())
    period_end = timezone.localdate()

    item_rows = _stock_analysis_item_totals(
        business, period_start, period_end, godown_id=godown_id, main_group=main_group
    )
    subgroups = defaultdict(lambda: {
        "id": None, "name": "(Direct items)",
        "inward_qty": Decimal("0"), "inward_value": Decimal("0"),
        "outward_qty": Decimal("0"), "outward_value": Decimal("0"),
    })
    for r in item_rows:
        sg = r["stock_group"]
        if sg and sg.parent_id == main_group.id:
            key = sg.id
            name = sg.name
            sid = sg.id
        else:
            key = 0
            name = "(Direct items)"
            sid = None
        row = subgroups[key]
        row["id"] = sid
        row["name"] = name
        row["inward_qty"] += r["inward_qty"]
        row["inward_value"] += r["inward_value"]
        row["outward_qty"] += r["outward_qty"]
        row["outward_value"] += r["outward_value"]

    rows = sorted(subgroups.values(), key=lambda x: x["name"].lower())
    for row in rows:
        row["inward_rate"] = (row["inward_value"] / row["inward_qty"]).quantize(Decimal("0.01")) if row["inward_qty"] else Decimal("0.00")
        row["outward_rate"] = (row["outward_value"] / row["outward_qty"]).quantize(Decimal("0.01")) if row["outward_qty"] else Decimal("0.00")

    totals = {
        "inward_qty": sum((r["inward_qty"] for r in rows), Decimal("0")),
        "inward_value": sum((r["inward_value"] for r in rows), Decimal("0")),
        "outward_qty": sum((r["outward_qty"] for r in rows), Decimal("0")),
        "outward_value": sum((r["outward_value"] for r in rows), Decimal("0")),
    }
    totals["inward_rate"] = (totals["inward_value"] / totals["inward_qty"]).quantize(Decimal("0.01")) if totals["inward_qty"] else Decimal("0.00")
    totals["outward_rate"] = (totals["outward_value"] / totals["outward_qty"]).quantize(Decimal("0.01")) if totals["outward_qty"] else Decimal("0.00")

    return render(request, "inventory/stock_analysis_sub.html", {
        "business": business,
        "main_group": main_group,
        "rows": rows,
        "totals": totals,
        "period_start": period_start,
        "period_end": period_end,
        "selected_godown_id": godown_id or "",
    })


@login_required
def stock_analysis_items(request, pk: int):
    """Movement analysis by items within a sub group."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    subgroup = get_object_or_404(StockGroup.objects.select_related("parent"), pk=pk, business=business, parent__isnull=False)
    godown_id = request.GET.get("godown")
    period_start = financial_year_start(timezone.localdate())
    period_end = timezone.localdate()
    rows = _stock_analysis_item_totals(
        business, period_start, period_end, godown_id=godown_id, sub_group=subgroup
    )
    rows = sorted(rows, key=lambda x: x["item_sku"].lower())
    totals = {
        "inward_qty": sum((r["inward_qty"] for r in rows), Decimal("0")),
        "inward_value": sum((r["inward_value"] for r in rows), Decimal("0")),
        "outward_qty": sum((r["outward_qty"] for r in rows), Decimal("0")),
        "outward_value": sum((r["outward_value"] for r in rows), Decimal("0")),
    }
    totals["inward_rate"] = (totals["inward_value"] / totals["inward_qty"]).quantize(Decimal("0.01")) if totals["inward_qty"] else Decimal("0.00")
    totals["outward_rate"] = (totals["outward_value"] / totals["outward_qty"]).quantize(Decimal("0.01")) if totals["outward_qty"] else Decimal("0.00")

    return render(request, "inventory/stock_analysis_items.html", {
        "business": business,
        "subgroup": subgroup,
        "rows": rows,
        "totals": totals,
        "period_start": period_start,
        "period_end": period_end,
        "selected_godown_id": godown_id or "",
    })


@login_required
def stock_analysis_item_movement(request, pk: int):
    """Item movement analysis (inward/outward sections) for one item."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(Item.objects.select_related("stock_group__parent"), pk=pk, business=business)
    godown_id = request.GET.get("godown")
    period_start = financial_year_start(timezone.localdate())
    period_end = timezone.localdate()

    entries = StockLedgerEntry.objects.filter(
        business=business,
        item=item,
        is_posted=True,
        posting_date__gte=period_start,
        posting_date__lte=period_end,
    ).order_by("posting_date", "id")
    if godown_id:
        entries = entries.filter(godown_id=godown_id)

    voucher_ids = [e.voucher_id for e in entries if e.voucher_id]
    purchase_labels, sales_labels = _movement_label_maps(voucher_ids)

    inward_map = defaultdict(lambda: {"name": "", "qty": Decimal("0"), "value": Decimal("0")})
    outward_map = defaultdict(lambda: {"name": "", "qty": Decimal("0"), "value": Decimal("0")})

    for e in entries:
        if e.qty_in and e.qty_in > 0:
            if e.voucher_type == "OPENING":
                label = "Opening Balance"
            elif e.voucher_type == "PURCHASE":
                label = purchase_labels.get(e.voucher_id) or "Suppliers"
            elif e.voucher_type == "STOCK_JOURNAL":
                label = "Stock Journal Inward"
            else:
                label = e.voucher_type.title() if e.voucher_type else "Inward"
            row = inward_map[label]
            row["name"] = label
            row["qty"] += e.qty_in
            row["value"] += (e.amount or Decimal("0"))

        if e.qty_out and e.qty_out > 0:
            if e.voucher_type == "SALES":
                label = sales_labels.get(e.voucher_id) or "Buyers"
            elif e.voucher_type == "STOCK_JOURNAL":
                label = "Stock Journal Outward"
            else:
                label = e.voucher_type.title() if e.voucher_type else "Outward"
            row = outward_map[label]
            row["name"] = label
            row["qty"] += e.qty_out
            row["value"] += (e.amount or Decimal("0"))

    inward_rows = sorted(inward_map.values(), key=lambda x: x["name"].lower())
    outward_rows = sorted(outward_map.values(), key=lambda x: x["name"].lower())
    for r in inward_rows:
        r["basic_rate"] = (r["value"] / r["qty"]).quantize(Decimal("0.01")) if r["qty"] else Decimal("0.00")
        r["effective_rate"] = r["basic_rate"]
    for r in outward_rows:
        r["basic_rate"] = (r["value"] / r["qty"]).quantize(Decimal("0.01")) if r["qty"] else Decimal("0.00")
        r["effective_rate"] = r["basic_rate"]

    inward_qty_total = sum((r["qty"] for r in inward_rows), Decimal("0"))
    inward_value_total = sum((r["value"] for r in inward_rows), Decimal("0"))
    outward_qty_total = sum((r["qty"] for r in outward_rows), Decimal("0"))
    outward_value_total = sum((r["value"] for r in outward_rows), Decimal("0"))
    totals = {
        "inward_qty": inward_qty_total,
        "inward_value": inward_value_total,
        "inward_effective_rate": (inward_value_total / inward_qty_total).quantize(Decimal("0.01")) if inward_qty_total else Decimal("0.00"),
        "outward_qty": outward_qty_total,
        "outward_value": outward_value_total,
        "outward_effective_rate": (outward_value_total / outward_qty_total).quantize(Decimal("0.01")) if outward_qty_total else Decimal("0.00"),
    }

    return render(request, "inventory/stock_analysis_item_movement.html", {
        "business": business,
        "item": item,
        "period_start": period_start,
        "period_end": period_end,
        "inward_rows": inward_rows,
        "outward_rows": outward_rows,
        "totals": totals,
        "selected_godown_id": godown_id or "",
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
