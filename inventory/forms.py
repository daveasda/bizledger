from decimal import Decimal
import json
from django import forms
from django.forms import modelformset_factory
from .models import StockGroup, Item, UnitOfMeasure, StandardRate, Godown


class StockGroupForm(forms.ModelForm):
    class Meta:
        model = StockGroup
        fields = ["name", "alias", "parent"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border rounded", "placeholder": ""}),
            "alias": forms.TextInput(attrs={"class": "w-full px-3 py-2 border rounded", "placeholder": ""}),
            "parent": forms.Select(attrs={"class": "w-full px-3 py-2 border rounded"}),
        }
        labels = {
            "name": "Name (alias)",
            "alias": "",
            "parent": "Under",
        }

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop("business", None)
        self.group_type = kwargs.pop("group_type", "any")  # any | main | sub
        super().__init__(*args, **kwargs)
        if self.business:
            qs = StockGroup.objects.filter(
                business=self.business, parent__isnull=True
            ).order_by("name")
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if self.group_type == "main":
                self.fields["parent"].queryset = StockGroup.objects.none()
                self.fields["parent"].empty_label = "Primary"
                self.fields["parent"].required = False
                self.fields["parent"].widget.attrs["disabled"] = "disabled"
            elif self.group_type == "sub":
                self.fields["parent"].queryset = qs
                self.fields["parent"].empty_label = "Select Main Group"
                self.fields["parent"].required = True
            else:
                self.fields["parent"].queryset = qs
                self.fields["parent"].empty_label = "Primary"
                self.fields["parent"].required = False
        if not self.instance.pk:
            self.fields["parent"].initial = None  # Primary

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if self.group_type == "main":
            return None
        if self.group_type == "sub" and not parent:
            raise forms.ValidationError("Please choose a main group.")
        # Always enforce two-level hierarchy: parent must be a main group.
        if parent and parent.parent_id is not None:
            raise forms.ValidationError("Sub groups can only be created under main groups.")
        return parent


class StockItemForm(forms.ModelForm):
    main_group = forms.ModelChoiceField(
        queryset=StockGroup.objects.none(),
        required=False,
        label="Main Group",
        widget=forms.Select(attrs={"class": "w-full px-3 py-2 border rounded"}),
    )
    sub_group = forms.ModelChoiceField(
        queryset=StockGroup.objects.none(),
        required=False,
        label="Sub Group",
        widget=forms.Select(attrs={"class": "w-full px-3 py-2 border rounded"}),
    )


    class Meta:
        model = Item
        fields = [
            "sku",
            "alias",
            "stock_group",
            "unit",
            "reorder_level",
            "opening_qty",
            "opening_rate",
            "opening_per",
            "opening_value",
        ]
        widgets = {
            "sku": forms.TextInput(attrs={"class": "w-full px-3 py-2 border rounded", "placeholder": ""}),
            "alias": forms.TextInput(attrs={"class": "w-full px-3 py-2 border rounded", "placeholder": ""}),
            "stock_group": forms.Select(attrs={"class": "w-full px-3 py-2 border rounded"}),
            "unit": forms.Select(attrs={"class": "w-full px-3 py-2 border rounded"}),
            "reorder_level": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border rounded", "step": "0.01"}),
            "opening_qty": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border rounded", "step": "0.001"}),
            "opening_rate": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border rounded", "step": "0.01"}),
            "opening_per": forms.TextInput(attrs={"class": "w-full px-3 py-2 border rounded", "placeholder": "Nos"}),
            "opening_value": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border rounded", "step": "0.01"}),
        }
        labels = {
            "sku": "Name (alias)",
            "alias": "",
            "stock_group": "Under",
            "unit": "Units",
            "reorder_level": "Reorder Level",
            "opening_qty": "Quantity",
            "opening_rate": "Rate",
            "opening_per": "per",
            "opening_value": "Value",
        }

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if self.business:
            main_groups = StockGroup.objects.filter(
                business=self.business, parent__isnull=True
            ).order_by("name")
            self.fields["main_group"].queryset = main_groups
            self.fields["main_group"].empty_label = "Select Main Group"
            self.fields["main_group"].required = True

            if self.instance and self.instance.pk and self.instance.stock_group_id:
                sg = self.instance.stock_group
                selected_main = sg.parent if sg.parent_id else sg
                selected_sub = sg if sg.parent_id else None
            else:
                selected_main = None
                selected_sub = None

            if self.is_bound:
                main_id = self.data.get("main_group") or None
                sub_id = self.data.get("sub_group") or None
                if main_id:
                    try:
                        selected_main = main_groups.get(pk=main_id)
                    except (StockGroup.DoesNotExist, ValueError, TypeError):
                        selected_main = None
                if sub_id:
                    try:
                        selected_sub = StockGroup.objects.get(
                            business=self.business, pk=sub_id
                        )
                    except (StockGroup.DoesNotExist, ValueError, TypeError):
                        selected_sub = None

            if selected_main:
                subgroups = StockGroup.objects.filter(
                    business=self.business, parent=selected_main
                ).order_by("name")
            else:
                subgroups = StockGroup.objects.none()
            self.fields["sub_group"].queryset = subgroups
            self.fields["sub_group"].empty_label = "Select Sub Group"
            self.fields["sub_group"].required = True

            subgroup_map = {
                str(g.pk): [{"id": s.pk, "name": s.name} for s in g.children.all().order_by("name")]
                for g in main_groups.prefetch_related("children")
            }
            self.fields["sub_group"].widget.attrs["data-subgroups"] = json.dumps(subgroup_map)

            if selected_main:
                self.fields["main_group"].initial = selected_main.pk
            if selected_sub:
                self.fields["sub_group"].initial = selected_sub.pk

            self.fields["stock_group"].required = False
            self.fields["stock_group"].widget = forms.HiddenInput()
            self.fields["unit"].queryset = UnitOfMeasure.objects.filter(business=self.business).order_by("symbol")
            self.fields["unit"].empty_label = "Not Applicable"
            self.fields["unit"].required = False

    def clean(self):
        cleaned = super().clean()
        main_group = cleaned.get("main_group")
        sub_group = cleaned.get("sub_group")

        if not main_group:
            self.add_error("main_group", "Please select a main group.")
            return cleaned
        if not sub_group:
            self.add_error("sub_group", "Please select a sub group.")
            return cleaned
        if sub_group.parent_id != main_group.id:
            self.add_error("sub_group", "Selected sub group does not belong to selected main group.")
            return cleaned
        cleaned["stock_group"] = sub_group
        return cleaned


class UnitOfMeasureForm(forms.ModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ["symbol", "formal_name", "decimal_places"]
        widgets = {
            "symbol": forms.TextInput(attrs={"class": "w-full px-3 py-2 border rounded", "placeholder": ""}),
            "formal_name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border rounded", "placeholder": ""}),
            "decimal_places": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border rounded", "min": 0}),
        }
        labels = {
            "symbol": "Symbol",
            "formal_name": "Formal name",
            "decimal_places": "Number of decimal places",
        }

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)


class StandardRateForm(forms.ModelForm):
    class Meta:
        model = StandardRate
        fields = ["applicable_from", "rate"]
        widgets = {
            "applicable_from": forms.DateInput(attrs={"class": "w-full px-2 py-1 border rounded", "type": "date"}),
            "rate": forms.NumberInput(attrs={"class": "w-full px-2 py-1 border rounded", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["applicable_from"].required = False
        self.fields["rate"].required = False


def get_standard_rate_formset(rate_type):
    """Return a formset for StandardRate filtered by rate_type."""
    return modelformset_factory(
        StandardRate,
        form=StandardRateForm,
        extra=1,          # show at most one blank row
        can_delete=True,  # allow deleting the existing row
        max_num=1,        # enforce only one entry per type
        validate_max=True,
    )


# --- Tally-style: Godowns and vouchers (Purchase, Sales, Stock Journal) ---


class GodownForm(forms.ModelForm):
    class Meta:
        model = Godown
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border rounded", "placeholder": "Godown name"}),
        }

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)


def _voucher_input_class():
    return "w-full px-3 py-2 border rounded"


# Purchase/Sales: one row in item table
class PurchaseRowForm(forms.Form):
    item = forms.ModelChoiceField(queryset=Item.objects.none(), widget=forms.Select(attrs={"class": _voucher_input_class()}))
    qty = forms.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"), widget=forms.NumberInput(attrs={"class": _voucher_input_class(), "step": "0.001"}))
    rate = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), widget=forms.NumberInput(attrs={"class": _voucher_input_class(), "step": "0.01"}))

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields["item"].queryset = Item.objects.filter(business=business, is_stock_item=True).order_by("sku")


def purchase_row_formset(business, data=None):
    FormSet = forms.formset_factory(PurchaseRowForm, extra=3, min_num=1, validate_min=True)
    formset = FormSet(data=data, form_kwargs={"business": business})
    return formset


class PurchaseVoucherForm(forms.Form):
    """Purchase with items: Party A/c, Purchase Ledger, Godown, date, optional supplier invoice no., narration."""
    party = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={"class": _voucher_input_class()}), label="Party A/c name")
    purchase_ledger = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={"class": _voucher_input_class()}), label="Purchase ledger")
    godown = forms.ModelChoiceField(queryset=Godown.objects.none(), widget=forms.Select(attrs={"class": _voucher_input_class()}), label="Godown")
    posting_date = forms.DateField(widget=forms.DateInput(attrs={"class": _voucher_input_class(), "type": "date"}), label="Date")
    supplier_invoice_no = forms.CharField(
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={"class": _voucher_input_class(), "placeholder": "Optional"}),
        label="Supplier invoice no.",
    )
    narration = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"class": _voucher_input_class(), "rows": 2}))

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            from ledger.models import Account
            self.fields["party"].queryset = Account.objects.filter(business=business, is_group=False).order_by("name")
            # Prefer EXPENSE accounts for Purchase Ledger; include purchase-named accounts if COA has wrong root_type
            from django.db.models import Q
            purchase_qs = Account.objects.filter(
                business=business, is_group=False
            ).filter(Q(root_type="EXPENSE") | Q(name__icontains="purchase")).order_by("name")
            if not purchase_qs.exists():
                purchase_qs = Account.objects.filter(business=business, is_group=False).order_by("name")
            self.fields["purchase_ledger"].queryset = purchase_qs
            self.fields["godown"].queryset = Godown.objects.filter(business=business).order_by("name")


class SalesVoucherForm(forms.Form):
    """Sales with items: Party A/c, Sales Ledger, Godown, date, narration."""
    party = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={"class": _voucher_input_class()}), label="Party A/c (Customer)")
    sales_ledger = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={"class": _voucher_input_class()}), label="Sales Ledger")
    godown = forms.ModelChoiceField(queryset=Godown.objects.none(), widget=forms.Select(attrs={"class": _voucher_input_class()}), label="Godown")
    posting_date = forms.DateField(widget=forms.DateInput(attrs={"class": _voucher_input_class(), "type": "date"}))
    narration = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"class": _voucher_input_class(), "rows": 2}))

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            from ledger.models import Account
            self.fields["party"].queryset = Account.objects.filter(business=business, is_group=False).order_by("name")
            # Prefer INCOME accounts for Sales Ledger; include sales-named accounts if COA has wrong root_type
            from django.db.models import Q
            sales_qs = Account.objects.filter(
                business=business, is_group=False
            ).filter(Q(root_type="INCOME") | Q(name__icontains="sales")).order_by("name")
            if not sales_qs.exists():
                sales_qs = Account.objects.filter(business=business, is_group=False).order_by("name")
            self.fields["sales_ledger"].queryset = sales_qs
            self.fields["godown"].queryset = Godown.objects.filter(business=business).order_by("name")


class StockJournalForm(forms.Form):
    """Stock Journal: From Godown -> To Godown."""
    item = forms.ModelChoiceField(queryset=Item.objects.none(), widget=forms.Select(attrs={"class": _voucher_input_class()}))
    from_godown = forms.ModelChoiceField(queryset=Godown.objects.none(), widget=forms.Select(attrs={"class": _voucher_input_class()}), label="From Godown")
    to_godown = forms.ModelChoiceField(queryset=Godown.objects.none(), widget=forms.Select(attrs={"class": _voucher_input_class()}), label="To Godown")
    qty = forms.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"), widget=forms.NumberInput(attrs={"class": _voucher_input_class(), "step": "0.001"}))
    rate = forms.DecimalField(required=False, max_digits=14, decimal_places=2, min_value=Decimal("0"), widget=forms.NumberInput(attrs={"class": _voucher_input_class(), "step": "0.01"}))
    posting_date = forms.DateField(widget=forms.DateInput(attrs={"class": _voucher_input_class(), "type": "date"}))
    narration = forms.CharField(required=False, max_length=500, widget=forms.TextInput(attrs={"class": _voucher_input_class(), "placeholder": "Optional"}))

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields["item"].queryset = Item.objects.filter(business=business, is_stock_item=True).order_by("sku")
            qs = Godown.objects.filter(business=business).order_by("name")
            self.fields["from_godown"].queryset = qs
            self.fields["to_godown"].queryset = qs
        self.fields["rate"].initial = Decimal("0")

    def clean(self):
        data = super().clean()
        fg = data.get("from_godown")
        tg = data.get("to_godown")
        if fg and tg and fg.pk == tg.pk:
            raise forms.ValidationError("From Godown and To Godown must be different.")
        return data
