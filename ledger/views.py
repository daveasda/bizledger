from decimal import Decimal
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Prefetch, Sum
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .constants import LEDGERS_IN_OPENING_BAL_TOTAL
from .forms import AccountForm, VoucherForm, VoucherLineFormSet
from .forms_voucher_entry import VoucherEntryHeaderForm, ParticularFormSet
from .models import Account, Voucher, VoucherLine
from .utils import build_account_tree, get_active_business_id

# If your Business model lives elsewhere:
from org.models import Business


def _get_business_or_redirect(request):
    """Get active business or redirect to business selection. Returns (business, redirect_response)."""
    bid = get_active_business_id(request)
    if not bid:
        return None, HttpResponseRedirect(reverse("org:select_business"))
    return get_object_or_404(Business, id=bid), None


def _opening_balance_totals(business):
    """Sum opening balances (Dr/Cr) for ledgers in Bank Accounts, Cash-in-Hand, Capital Account."""
    ledgers = Account.objects.filter(
        business=business,
        is_group=False,
        parent__name__in=LEDGERS_IN_OPENING_BAL_TOTAL,
    ).select_related("parent")
    total_dr = Decimal("0.00")
    total_cr = Decimal("0.00")
    for acc in ledgers:
        amt = acc.opening_balance or Decimal("0.00")
        if amt <= 0:
            continue
        if (acc.opening_balance_type or "DR") == "DR":
            total_dr += amt
        else:
            total_cr += amt
    return total_dr, total_cr


def _format_drcr(net: Decimal):
    net = net or Decimal("0.00")
    if net >= 0:
        return str(net.quantize(Decimal("0.01"))), "Dr"
    return str((-net).quantize(Decimal("0.01"))), "Cr"


def api_account_balance(request, account_id: int):
    """Return current balance (posted vouchers only) for a ledger. Used for Cur Bal Dr/Cr and live preview."""
    bid = get_active_business_id(request)
    if not bid:
        return JsonResponse({"error": "No business selected"}, status=404)
    business = get_object_or_404(Business, id=bid)
    acc = get_object_or_404(Account, id=account_id, business=business, is_group=False)

    qs = VoucherLine.objects.filter(
        voucher__business=business,
        voucher__is_posted=True,
        account=acc,
    )
    agg = qs.aggregate(
        dr=Sum("debit", default=Decimal("0.00")),
        cr=Sum("credit", default=Decimal("0.00")),
    )
    net = (agg["dr"] or Decimal("0.00")) - (agg["cr"] or Decimal("0.00"))
    amt, drcr = _format_drcr(net)

    return JsonResponse({
        "account_id": acc.id,
        "amount": amt,
        "drcr": drcr,
        "net": str(net.quantize(Decimal("0.01"))),
    })


def gateway(request):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    
    # quick stats
    accounts_count = Account.objects.filter(business=business).count()
    draft_vouchers = Voucher.objects.filter(business=business, is_posted=False).count()
    posted_vouchers = Voucher.objects.filter(business=business, is_posted=True).count()

    return render(request, "ledger/gateway.html", {
        "business": business,
        "accounts_count": accounts_count,
        "draft_vouchers": draft_vouchers,
        "posted_vouchers": posted_vouchers,
    })


def accounts_gateway(request):
    """Tally-style Accounts Gateway showing Groups, Ledgers, Voucher Types"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    return render(request, "ledger/accounts_gateway.html", {
        "business": business,
    })


def groups_display(request):
    """Display list of Groups"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    groups = Account.objects.filter(business=business, is_group=True).order_by("name")
    return render(request, "ledger/groups_display.html", {
        "business": business,
        "groups": groups,
    })


@require_http_methods(["GET", "POST"])
def group_create(request):
    """Create a new Group"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = AccountForm(request.POST or None, business=business, include_root_groups=True)
    # For groups, set default: behaves_like_subledger = False (so is_group = True)
    if not request.POST:
        form.fields["behaves_like_subledger"].initial = False
    if request.method == "POST" and form.is_valid():
        acc = form.save(commit=False)
        acc.business = business
        acc.is_group = True  # Groups are always is_group=True
        acc.save()
        messages.success(request, "Group created.")
        return redirect("ledger:groups_display")
    return render(request, "ledger/group_form.html", {
        "business": business,
        "form": form,
        "title": "Group Creation",
    })


@require_http_methods(["GET", "POST"])
def group_alter(request, pk: int):
    """Alter an existing Group"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    group = get_object_or_404(Account, pk=pk, business=business, is_group=True)
    form = AccountForm(request.POST or None, instance=group, business=business, include_root_groups=True)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Group updated.")
        return redirect("ledger:groups_display")
    return render(request, "ledger/group_form.html", {
        "business": business,
        "form": form,
        "title": "Group Alteration",
    })


def group_summary(request, pk: int):
    """Group Summary: all ledgers under this group with closing Debit/Credit balances and grand total."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    group = get_object_or_404(Account, pk=pk, business=business, is_group=True)
    ledgers = Account.objects.filter(parent=group, business=business, is_group=False).order_by("name")
    # Aggregate posted voucher lines per ledger: account_id -> (total_dr, total_cr)
    agg_qs = (
        VoucherLine.objects.filter(
            account__in=ledgers,
            voucher__business=business,
            voucher__is_posted=True,
        )
        .values("account_id")
        .annotate(total_dr=Sum("debit"), total_cr=Sum("credit"))
    )
    agg_by_account = {
        r["account_id"]: (
            r["total_dr"] or Decimal("0.00"),
            r["total_cr"] or Decimal("0.00"),
        )
        for r in agg_qs
    }
    rows = []
    grand_dr = Decimal("0.00")
    grand_cr = Decimal("0.00")
    for ledger in ledgers:
        op_bal = ledger.opening_balance or Decimal("0.00")
        op_type = ledger.opening_balance_type or "DR"
        opening_net = -op_bal if op_type == "CR" else op_bal
        total_dr, total_cr = agg_by_account.get(ledger.id, (Decimal("0.00"), Decimal("0.00")))
        closing_net = opening_net + total_dr - total_cr
        closing_dr = closing_net if closing_net > 0 else Decimal("0.00")
        closing_cr = -closing_net if closing_net < 0 else Decimal("0.00")
        rows.append({
            "ledger": ledger,
            "closing_dr": closing_dr,
            "closing_cr": closing_cr,
        })
        grand_dr += closing_dr
        grand_cr += closing_cr
    return render(request, "ledger/group_summary.html", {
        "business": business,
        "group": group,
        "rows": rows,
        "grand_total_dr": grand_dr,
        "grand_total_cr": grand_cr,
    })


def ledgers_display(request):
    """Display list of Ledgers"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    ledgers = Account.objects.filter(business=business, is_group=False).order_by("name")
    return render(request, "ledger/ledgers_display.html", {
        "business": business,
        "ledgers": ledgers,
    })


@require_http_methods(["GET", "POST"])
def ledger_create(request):
    """Create a new Ledger"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    data = request.POST if request.method == "POST" else None
    if data is not None:
        data = data.copy()
        data["behaves_like_subledger"] = True  # Ledgers are always is_group=False
    form = AccountForm(data, business=business, include_root_groups=False)
    # For ledgers, set default: behaves_like_subledger = True (so is_group = False)
    if not request.POST:
        form.fields["behaves_like_subledger"].initial = True
    if request.method == "POST" and form.is_valid():
        acc = form.save(commit=False)
        acc.business = business
        acc.is_group = False  # Ledgers are always is_group=False (must appear in ledgers display)
        try:
            acc.save()
            # Force is_group=False in DB in case form/model defaulted it to True
            Account.objects.filter(pk=acc.pk, business=business).update(is_group=False)
        except IntegrityError:
            messages.error(
                request,
                "An account with this name already exists for this business. "
                "Use a different name or alter the existing one under Groups/Ledgers Display.",
            )
            total_op_dr, total_op_cr = _opening_balance_totals(business)
            return render(request, "ledger/ledger_form.html", {
                "business": business,
                "form": form,
                "title": "Ledger Creation",
                "hide_nature_of_group": True,
                "total_op_dr": total_op_dr,
                "total_op_cr": total_op_cr,
            })
        except ValidationError as e:
            if hasattr(e, "message_dict"):
                for field, msgs in e.message_dict.items():
                    for msg in (msgs if isinstance(msgs, (list, tuple)) else [msgs]):
                        messages.error(request, f"{field}: {msg}")
            else:
                messages.error(request, str(e))
            total_op_dr, total_op_cr = _opening_balance_totals(business)
            return render(request, "ledger/ledger_form.html", {
                "business": business,
                "form": form,
                "title": "Ledger Creation",
                "hide_nature_of_group": True,
                "total_op_dr": total_op_dr,
                "total_op_cr": total_op_cr,
            })
        messages.success(request, "Ledger created.")
        return redirect("ledger:ledgers_display")
    if request.method == "POST":
        messages.error(request, "Could not save ledger. Please fix the errors below.")
    total_op_dr, total_op_cr = _opening_balance_totals(business)
    return render(request, "ledger/ledger_form.html", {
        "business": business,
        "form": form,
        "title": "Ledger Creation",
        "hide_nature_of_group": True,
        "total_op_dr": total_op_dr,
        "total_op_cr": total_op_cr,
    })


@require_http_methods(["GET", "POST"])
def ledger_alter(request, pk: int):
    """Alter an existing Ledger"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    ledger = get_object_or_404(Account, pk=pk, business=business, is_group=False)
    data = request.POST if request.method == "POST" else None
    if data is not None:
        data = data.copy()
        data["behaves_like_subledger"] = True  # Ledgers stay is_group=False
    form = AccountForm(data, instance=ledger, business=business, include_root_groups=False)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ledger updated.")
        return redirect("ledger:ledgers_display")
    total_op_dr, total_op_cr = _opening_balance_totals(business)
    return render(request, "ledger/ledger_form.html", {
        "business": business,
        "form": form,
        "ledger": ledger,
        "title": "Ledger Alteration",
        "hide_nature_of_group": True,
        "total_op_dr": total_op_dr,
        "total_op_cr": total_op_cr,
    })


def ledger_voucher_details(request, pk: int):
    """Ledger Voucher Details - all transactions for a ledger with balance totals."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response

    ledger = get_object_or_404(Account, pk=pk, business=business, is_group=False)

    # All posted voucher lines for this ledger, ordered by date
    lines = (
        VoucherLine.objects.filter(
            account=ledger,
            voucher__business=business,
            voucher__is_posted=True,
        )
        .select_related("voucher")
        .prefetch_related(
            Prefetch("voucher__lines", queryset=VoucherLine.objects.select_related("account"))
        )
        .order_by("voucher__posting_date", "voucher__id", "id")
    )

    # Build transaction rows: Date, Particulars, Vch Type, Vch No., Debit, Credit
    transactions = []
    opening_net = Decimal("0.00")
    op_bal = ledger.opening_balance or Decimal("0.00")
    op_type = ledger.opening_balance_type or "DR"
    if op_type == "CR":
        opening_net = -op_bal
    else:
        opening_net = op_bal

    running = opening_net
    for line in lines:
        running += line.debit - line.credit
        amt, drcr = _format_drcr(running)
        # Particulars: for Purchase/Sales vouchers use the selected Purchase/Sales ledger (dropdown value)
        particulars = line.voucher.narration or line.memo or "-"
        if particulars == "-" and line.voucher.voucher_type in ("PURCHASE", "SALES"):
            for other in line.voucher.lines.all():
                if other.account_id == ledger.id:
                    continue
                # PURCHASE: dropdown is the Dr line (purchase ledger); SALES: dropdown is the Cr line (sales ledger)
                if line.voucher.voucher_type == "PURCHASE" and other.debit > 0:
                    particulars = other.account.name
                    break
                if line.voucher.voucher_type == "SALES" and other.credit > 0:
                    particulars = other.account.name
                    break
        transactions.append({
            "date": line.voucher.posting_date,
            "particulars": particulars,
            "vch_type": line.voucher.get_voucher_type_display(),
            "vch_no": line.voucher.number,
            "debit": line.debit,
            "credit": line.credit,
            "voucher_id": line.voucher_id,
            "running_balance": amt,
            "running_drcr": drcr,
        })

    total_dr = sum(t["debit"] for t in transactions)
    total_cr = sum(t["credit"] for t in transactions)
    closing_net = opening_net + total_dr - total_cr

    opening_amt, opening_drcr = _format_drcr(opening_net)
    closing_amt, closing_drcr = _format_drcr(closing_net)

    return render(request, "ledger/ledger_voucher_details.html", {
        "business": business,
        "ledger": ledger,
        "transactions": transactions,
        "opening_balance": opening_amt,
        "opening_drcr": opening_drcr,
        "closing_balance": closing_amt,
        "closing_drcr": closing_drcr,
        "total_dr": total_dr,
        "total_cr": total_cr,
    })


def voucher_types_display(request):
    """Display list of Voucher Types"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    from .models import VoucherType
    voucher_types = [{"value": choice[0], "label": choice[1]} for choice in VoucherType.choices]
    return render(request, "ledger/voucher_types_display.html", {
        "business": business,
        "voucher_types": voucher_types,
    })


@require_http_methods(["GET", "POST"])
def voucher_type_create(request):
    """Voucher Types are predefined, so this just shows info"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    messages.info(request, "Voucher Types are predefined. Available types: Receipt, Payment, Journal, Contra, Sales.")
    return redirect("ledger:voucher_types_display")


@require_http_methods(["GET", "POST"])
def voucher_type_alter(request, pk: int):
    """Voucher Types are predefined, so this just shows info"""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    messages.info(request, "Voucher Types are predefined and cannot be altered.")
    return redirect("ledger:voucher_types_display")


@require_http_methods(["GET", "POST"])
def account_create(request):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    form = AccountForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        acc = form.save(commit=False)
        acc.business = business
        acc.save()
        messages.success(request, "Account created.")
        return redirect("ledger:accounts_gateway")
    return render(request, "ledger/account_form.html", {
        "business": business,
        "form": form,
        "title": "Create Account",
    })


@require_http_methods(["GET", "POST"])
def account_edit(request, pk: int):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    acc = get_object_or_404(Account, pk=pk, business=business)
    form = AccountForm(request.POST or None, instance=acc, business=business)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Account updated.")
        return redirect("ledger:accounts_gateway")
    return render(request, "ledger/account_form.html", {
        "business": business,
        "form": form,
        "title": "Alter Account",
    })


def voucher_list(request):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    vouchers = Voucher.objects.filter(business=business).order_by("-posting_date", "-id")[:200]
    return render(request, "ledger/voucher_list.html", {
        "business": business,
        "vouchers": vouchers,
    })


@require_http_methods(["GET", "POST"])
def voucher_entry(request, vtype: str):
    """
    Tally-style Receipt/Payment entry:
      - User selects one top Account (Cash/Bank)
      - User enters only Particulars + Amount lines
      - System auto-creates one top line for the total
    """
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response

    vtype = (vtype or "").upper().strip()
    if vtype not in ("RECEIPT", "PAYMENT", "CONTRA", "SALES", "PURCHASE"):
        messages.error(request, "Only Receipt, Payment, Contra, Sales and Purchase are enabled.")
        return redirect("ledger:voucher_list")

    voucher = Voucher(business=business, voucher_type=vtype)
    header_form = VoucherEntryHeaderForm(request.POST or None, instance=voucher, business=business)
    formset = ParticularFormSet(request.POST or None, form_kwargs={"business": business})

    if request.method == "POST" and header_form.is_valid() and formset.is_valid():
        particulars = []
        for f in formset:
            cd = getattr(f, "cleaned_data", None)
            if not cd:
                continue
            if cd.get("DELETE"):
                continue

            acc = cd.get("account")
            amt = cd.get("amount")

            # Skip blank rows like Tally does
            if not acc or not amt:
                continue

            particulars.append({
                "account": acc,
                "amount": amt,
                "memo": (cd.get("memo") or "").strip(),
            })

        if not particulars:
            messages.error(request, "Enter at least one Particulars line with an amount.")
            return render(request, "ledger/voucher_entry.html", {
                "business": business,
                "vtype": vtype,
                "header_form": header_form,
                "formset": formset,
            })

        total = sum((p["amount"] for p in particulars), Decimal("0.00"))
        top_account = header_form.cleaned_data["account"]

        try:
            with transaction.atomic():
                v = header_form.save(commit=False)
                v.business = business
                v.voucher_type = vtype
                # Simple numbering (replace later with per-type sequence)
                if not getattr(v, "number", None):
                    v.number = str(Voucher.objects.filter(business=business).count() + 1)
                v.save()

                # One auto top line + particulars
                # CONTRA default = deposit (receipt-style); contra_direction=withdraw = payment-style
                contra_withdraw = request.POST.get("contra_direction") == "withdraw"
                receipt_style = vtype in ("RECEIPT", "SALES") or (vtype == "CONTRA" and not contra_withdraw)
                # PURCHASE is payment-style (top account Cr, particulars Dr)

                if receipt_style:
                    # Top account receives (Dr), particulars give (Cr) — e.g. deposit to bank
                    VoucherLine.objects.create(
                        voucher=v,
                        account=top_account,
                        debit=total,
                        credit=Decimal("0.00"),
                        memo="",
                    )
                    for p in particulars:
                        VoucherLine.objects.create(
                            voucher=v,
                            account=p["account"],
                            debit=Decimal("0.00"),
                            credit=p["amount"],
                            memo=p["memo"],
                        )
                else:
                    # Top account gives (Cr), particulars receive (Dr) — e.g. payment or contra withdraw
                    VoucherLine.objects.create(
                        voucher=v,
                        account=top_account,
                        debit=Decimal("0.00"),
                        credit=total,
                        memo="",
                    )
                    for p in particulars:
                        VoucherLine.objects.create(
                            voucher=v,
                            account=p["account"],
                            debit=p["amount"],
                            credit=Decimal("0.00"),
                            memo=p["memo"],
                        )

                # Tally-like: Accept posts (locks) immediately
                v.post(user=request.user)
        except ValidationError as e:
            messages.error(request, str(e))
            return render(request, "ledger/voucher_entry.html", {
                "business": business,
                "vtype": vtype,
                "header_form": header_form,
                "formset": formset,
            })

        messages.success(request, f"{vtype.title()} voucher posted (locked).")
        return redirect("ledger:voucher_detail", pk=v.pk)

    return render(request, "ledger/voucher_entry.html", {
        "business": business,
        "vtype": vtype,
        "header_form": header_form,
        "formset": formset,
    })


@require_http_methods(["GET", "POST"])
def voucher_create(request):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    v = Voucher(business=business)  # draft
    form = VoucherForm(request.POST or None, instance=v)
    formset = VoucherLineFormSet(request.POST or None, instance=v)

    # Limit account choices to ledger accounts in this business
    ledger_qs = Account.objects.filter(business=business, is_group=False).order_by("name")
    for f in formset.forms:
        if "account" in f.fields:
            f.fields["account"].queryset = ledger_qs

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                v = form.save(commit=False)
                v.business = business
                # You can generate number later; for now simple:
                if not getattr(v, "number", None):
                    v.number = str((Voucher.objects.filter(business=business).count()) + 1)
                v.save()
                formset.instance = v
                formset.save()
            messages.success(request, "Voucher saved (draft).")
            return redirect("ledger:voucher_detail", pk=v.pk)

    return render(request, "ledger/voucher_form.html", {
        "business": business,
        "form": form,
        "formset": formset,
        "title": "New Voucher",
    })


def voucher_detail(request, pk: int):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    v = get_object_or_404(Voucher, pk=pk, business=business)
    lines = v.lines.select_related("account").all()

    totals = lines.aggregate(
        dr=Sum("debit", default=Decimal("0.00")),
        cr=Sum("credit", default=Decimal("0.00")),
    )
    dr = totals["dr"] or Decimal("0.00")
    cr = totals["cr"] or Decimal("0.00")

    return render(request, "ledger/voucher_detail.html", {
        "business": business,
        "v": v,
        "lines": lines,
        "dr": dr,
        "cr": cr,
        "balanced": dr == cr,
    })


@require_http_methods(["GET", "POST"])
def voucher_edit(request, pk: int):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    v = get_object_or_404(Voucher, pk=pk, business=business)

    if v.is_posted:
        messages.error(request, "Posted vouchers are locked.")
        return redirect("ledger:voucher_detail", pk=v.pk)

    form = VoucherForm(request.POST or None, instance=v)
    formset = VoucherLineFormSet(request.POST or None, instance=v)

    ledger_qs = Account.objects.filter(business=business, is_group=False).order_by("name")
    for f in formset.forms:
        if "account" in f.fields:
            f.fields["account"].queryset = ledger_qs

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, "Voucher updated.")
            return redirect("ledger:voucher_detail", pk=v.pk)

    return render(request, "ledger/voucher_form.html", {
        "business": business,
        "form": form,
        "formset": formset,
        "title": f"Edit Voucher {v.number}",
    })


@require_http_methods(["POST"])
def voucher_post(request, pk: int):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    v = get_object_or_404(Voucher, pk=pk, business=business)

    if v.is_posted:
        messages.info(request, "Already posted.")
        return redirect("ledger:voucher_detail", pk=v.pk)

    # Use the model's post() method which handles all validation
    try:
        v.post(user=request.user)
        messages.success(request, "Voucher posted (locked).")
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"Error posting voucher: {str(e)}")
    return redirect("ledger:voucher_detail", pk=v.pk)


@require_http_methods(["POST"])
def voucher_delete(request, pk: int):
    """Delete a voucher (draft or posted). For PURCHASE/SALES, also removes related stock entries."""
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response
    v = get_object_or_404(Voucher, pk=pk, business=business)
    try:
        with transaction.atomic():
            # Remove inventory stock entries that reference this voucher (PURCHASE/SALES from inventory)
            from inventory.models import StockLedgerEntry
            StockLedgerEntry.objects.filter(
                business=business,
                voucher_type__in=("PURCHASE", "SALES"),
                voucher_id=v.id,
                is_posted=True,
            ).delete()
            v.delete()
        messages.success(request, f"Voucher {v.number} deleted.")
    except Exception as e:
        messages.error(request, f"Could not delete voucher: {e}")
    return redirect("ledger:voucher_list")


@require_http_methods(["POST"])
def install_coa(request):
    business, redirect_response = _get_business_or_redirect(request)
    if redirect_response:
        return redirect_response

    # Don't overwrite if accounts exist
    if Account.objects.filter(business=business).exists():
        messages.error(request, "Accounts already exist for this business.")
        return redirect("ledger:gateway")

    # Minimal "Tally-ish" COA starter
    coa = {
        "Assets": {
            "Cash-in-Hand": {"Cash": {}},
            "Bank Accounts": {},
        },
        "Liabilities": {
            "Duties & Taxes": {},
            "Sundry Creditors": {},
        },
        "Income": {
            "Sales": {},
        },
        "Expenses": {
            "Purchase": {},
            "Indirect Expenses": {"Rent": {}, "Electricity": {}},
        },
    }

    # Root type mapping
    roots = {
        "Assets": "ASSET",
        "Liabilities": "LIABILITY",
        "Income": "INCOME",
        "Expenses": "EXPENSE",
    }

    def create_node(name, parent, root_type):
        # group if has children else ledger
        return Account.objects.create(
            business=business,
            name=name,
            parent=parent,
            is_group=True,  # default, corrected below
            root_type=root_type,
            account_type="",
        )

    def walk(tree_dict, parent=None, root_name=None):
        for name, children in tree_dict.items():
            if parent is None:
                root_type = roots[name]
                node = Account.objects.create(
                    business=business,
                    name=name,
                    parent=None,
                    is_group=True,
                    root_type=root_type,
                    account_type="",
                )
                walk(children, parent=node, root_name=name)
            else:
                root_type = roots[root_name]
                node = Account.objects.create(
                    business=business,
                    name=name,
                    parent=parent,
                    is_group=True,  # will change to ledger if leaf
                    root_type=root_type,
                    account_type="",
                )
                if children:
                    walk(children, parent=node, root_name=root_name)
                else:
                    node.is_group = False
                    node.save(update_fields=["is_group"])

    with transaction.atomic():
        walk(coa)
        # Primary ledger (no group): stores current gross profit (Tally-style exception)
        Account.objects.get_or_create(
            business=business,
            name="Profit & Loss A/c",
            defaults={
                "parent": None,
                "is_group": False,
                "is_primary_ledger": True,
                "account_type": "",
            },
        )

    messages.success(request, "Chart of Accounts installed.")
    return redirect("ledger:accounts_gateway")
