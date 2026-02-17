from decimal import Decimal
from django import forms
from django.forms import formset_factory, inlineformset_factory
from .models import Account, Voucher, VoucherLine

# The four standard root groups: excluded from ledger "Under" dropdown only
STANDARD_ROOT_NAMES = ("Assets", "Liabilities", "Income", "Expenses")


class AccountForm(forms.ModelForm):
    is_primary = forms.BooleanField(required=False, label="Primary", help_text="Check if this is a primary (root) group")
    behaves_like_subledger = forms.BooleanField(required=False, label="Group behaves like a Sub-Ledger", initial=False)

    class Meta:
        model = Account
        fields = [
            "name", "parent", "is_group", "root_type", "account_type",
            "inventory_values_affected", "opening_balance", "opening_balance_type", "opening_balance_date",
            "mailing_name", "mailing_address", "mailing_state", "mailing_pin_code",
            "income_tax_no", "sales_tax_no"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none", "placeholder": ""}),
            "parent": forms.Select(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none"}),
            "is_group": forms.CheckboxInput(attrs={"class": "h-5 w-5"}),
            "root_type": forms.Select(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none"}),
            "account_type": forms.TextInput(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none"}),
            "inventory_values_affected": forms.CheckboxInput(attrs={"class": "h-5 w-5"}),
            "opening_balance": forms.NumberInput(attrs={"step": "0.01", "class": "w-full px-3 py-2 border-0 focus:outline-none", "placeholder": "0.00"}),
            "opening_balance_type": forms.Select(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none"}),
            "opening_balance_date": forms.DateInput(attrs={"type": "date", "class": "w-full px-3 py-2 border-0 focus:outline-none"}),
            "mailing_name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none", "placeholder": ""}),
            "mailing_address": forms.Textarea(attrs={"rows": 3, "class": "w-full px-3 py-2 border-0 focus:outline-none", "placeholder": ""}),
            "mailing_state": forms.TextInput(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none", "placeholder": ""}),
            "mailing_pin_code": forms.TextInput(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none", "placeholder": ""}),
            "income_tax_no": forms.TextInput(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none", "placeholder": ""}),
            "sales_tax_no": forms.TextInput(attrs={"class": "w-full px-3 py-2 border-0 focus:outline-none", "placeholder": ""}),
        }
        labels = {
            "name": "Name (alias)",
            "parent": "Under",
            "root_type": "Nature of Group",
            "is_group": "Group behaves like a Sub-Ledger",
            "inventory_values_affected": "Inventory values are affected",
            "opening_balance": "Opening Balance",
            "opening_balance_type": "Dr/Cr",
            "opening_balance_date": "Opening Balance Date",
            "mailing_name": "Name",
            "mailing_address": "Address",
            "mailing_state": "State",
            "mailing_pin_code": "PIN Code",
            "income_tax_no": "Income Tax No.",
            "sales_tax_no": "Sales Tax No.",
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        # For groups: include roots so you can put a new group "Under" Assets/Liabilities/etc.
        # For ledgers: exclude roots so "Under" lists only non-root groups (e.g. Capital Account)
        include_root_groups = kwargs.pop("include_root_groups", False)
        super().__init__(*args, **kwargs)
        if business:
            qs = Account.objects.filter(business=business, is_group=True).order_by("name")
            if not include_root_groups:
                # Exclude only the four standard roots; user primary groups (e.g. Capital Account) stay
                qs = qs.exclude(name__in=STANDARD_ROOT_NAMES)
            self.fields["parent"].queryset = qs
            self.fields["parent"].empty_label = "Select parent group..."

        # Make all fields optional except name and parent
        self.fields["root_type"].required = False
        self.fields["account_type"].required = False
        self.fields["inventory_values_affected"].required = False
        self.fields["opening_balance"].required = False
        self.fields["opening_balance_type"].required = False
        self.fields["opening_balance_date"].required = False
        self.fields["mailing_name"].required = False
        self.fields["mailing_address"].required = False
        self.fields["mailing_state"].required = False
        self.fields["mailing_pin_code"].required = False
        self.fields["income_tax_no"].required = False
        self.fields["sales_tax_no"].required = False

        # Set is_primary based on whether parent is None
        if self.instance and self.instance.pk:
            self.fields["is_primary"].initial = self.instance.parent is None
        else:
            self.fields["is_primary"].initial = False

        # Set behaves_like_subledger based on is_group (inverted)
        if self.instance and self.instance.pk:
            self.fields["behaves_like_subledger"].initial = not self.instance.is_group
        else:
            self.fields["behaves_like_subledger"].initial = False

    def clean(self):
        cleaned_data = super().clean()
        is_primary = cleaned_data.get("is_primary", False)
        parent = cleaned_data.get("parent")
        root_type = cleaned_data.get("root_type")

        # Handle behaves_like_subledger (inverted is_group)
        behaves_like_subledger = cleaned_data.get("behaves_like_subledger", False)
        cleaned_data["is_group"] = not behaves_like_subledger

        # For ledgers (is_group=False): parent is required unless primary ledger (e.g. Profit & Loss A/c)
        if not cleaned_data["is_group"] and not parent:
            if self.instance and getattr(self.instance, "is_primary_ledger", False):
                cleaned_data["parent"] = None
            else:
                raise forms.ValidationError({"parent": "Ledgers must have a parent group. Please select 'Under'."})

        # For groups without parent: root_type is required (it's a root)
        if not parent:
            if not root_type:
                raise forms.ValidationError({"root_type": "Root accounts must have a Nature of Group."})
        else:
            pass

        if is_primary and parent:
            raise forms.ValidationError("Primary groups cannot have a parent. Uncheck 'Primary' or remove the parent.")

        if is_primary:
            cleaned_data["parent"] = None

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
        return instance


class VoucherForm(forms.ModelForm):
    class Meta:
        model = Voucher
        fields = ["voucher_type", "posting_date", "narration"]
        widgets = {
            "voucher_type": forms.Select(attrs={"class": "w-full border rounded px-3 py-2"}),
            "posting_date": forms.DateInput(attrs={"type": "date", "class": "w-full border rounded px-3 py-2"}),
            "narration": forms.Textarea(attrs={"rows": 2, "class": "w-full border rounded px-3 py-2"}),
        }


class VoucherLineForm(forms.ModelForm):
    class Meta:
        model = VoucherLine
        fields = ["account", "debit", "credit", "memo"]
        widgets = {
            "account": forms.Select(attrs={"class": "w-full border rounded px-2 py-2"}),
            "debit": forms.NumberInput(attrs={"step": "0.01", "class": "w-full border rounded px-2 py-2"}),
            "credit": forms.NumberInput(attrs={"step": "0.01", "class": "w-full border rounded px-2 py-2"}),
            "memo": forms.TextInput(attrs={"class": "w-full border rounded px-2 py-2"}),
        }

    def clean(self):
        cleaned = super().clean()
        debit = cleaned.get("debit") or Decimal("0.00")
        credit = cleaned.get("credit") or Decimal("0.00")
        if debit > 0 and credit > 0:
            raise forms.ValidationError("A line cannot have both Debit and Credit.")
        if debit == 0 and credit == 0:
            raise forms.ValidationError("Enter either Debit or Credit.")
        return cleaned


VoucherLineFormSet = inlineformset_factory(
    Voucher,
    VoucherLine,
    form=VoucherLineForm,
    extra=4,
    can_delete=True,
)


# --- Purchase (header + items). Use defensive clean_purchase_date so it is never
# run on formset item forms (PurchaseItemForm), which don't have cleaned_data or purchase_date. ---

class PurchaseForm(forms.Form):
    """Header form for a purchase voucher. Do not subclass this for item forms."""
    purchase_date = forms.DateField(required=True, widget=forms.DateInput(attrs={"type": "date", "class": "w-full border rounded px-3 py-2"}))
    purchase_num = forms.CharField(required=False, max_length=64)
    supplier_name = forms.CharField(required=False, max_length=255)
    contact_no = forms.CharField(required=False, max_length=64)
    address = forms.CharField(required=False, max_length=512)
    state = forms.CharField(required=False, max_length=100)
    gst_number = forms.CharField(required=False, max_length=64)
    transport_charge = forms.DecimalField(required=False, initial=0, min_value=0, decimal_places=2, max_digits=14)
    labour_charge = forms.DecimalField(required=False, initial=0, min_value=0, decimal_places=2, max_digits=14)
    other_charge = forms.DecimalField(required=False, initial=0, min_value=0, decimal_places=2, max_digits=14)
    total_amount = forms.DecimalField(required=False, decimal_places=2, max_digits=14)
    payment_mode = forms.CharField(required=False, max_length=64)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def clean_purchase_date(self):
        # Defensive: this can be invoked when formset validates and the form in the loop
        # is a PurchaseItemForm (e.g. if it subclasses this). Only run on the main form.
        if "purchase_date" not in self.fields:
            return None
        cleaned_data = getattr(self, "cleaned_data", None)
        if cleaned_data is None:
            return None
        return cleaned_data.get("purchase_date")


class PurchaseItemForm(forms.Form):
    """Per-line item form. Do not subclass PurchaseForm so clean_purchase_date is never run on items."""
    item_name = forms.CharField(required=False, max_length=255)
    quantity = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=14)
    rate = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=14)
    amount = forms.DecimalField(required=False, decimal_places=2, max_digits=14)
    godown = forms.CharField(required=False, max_length=255)


PurchaseItemFormSet = formset_factory(PurchaseItemForm, extra=2, can_delete=True, max_num=1000)
