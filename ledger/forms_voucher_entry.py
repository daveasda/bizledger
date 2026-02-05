from decimal import Decimal

from django import forms
from django.forms import formset_factory

from .models import Account, Voucher


class VoucherEntryHeaderForm(forms.ModelForm):
    # Top "Account" (Cash/Bank). This is NOT a voucher line yet.
    account = forms.ModelChoiceField(queryset=Account.objects.none())

    class Meta:
        model = Voucher
        fields = ["posting_date", "narration"]
        widgets = {
            "posting_date": forms.DateInput(attrs={"type": "date", "class": "w-full border rounded px-3 py-2"}),
            "narration": forms.Textarea(attrs={"rows": 2, "class": "w-full border rounded px-3 py-2"}),
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            # Must be a ledger account (not group)
            self.fields["account"].queryset = Account.objects.filter(
                business=business,
                is_group=False,
            ).order_by("name")
        self.fields["account"].widget.attrs.update({"class": "w-full border rounded px-3 py-2"})


class ParticularLineForm(forms.Form):
    account = forms.ModelChoiceField(queryset=Account.objects.none())
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=14,
        required=False,
    )
    memo = forms.CharField(required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields["account"].queryset = Account.objects.filter(
                business=business,
                is_group=False,
            ).order_by("name")

        self.fields["account"].widget.attrs.update({"class": "w-full border rounded px-2 py-2"})
        self.fields["amount"].widget.attrs.update({"class": "w-full border rounded px-2 py-2", "step": "0.01"})
        self.fields["memo"].widget.attrs.update({"class": "w-full border rounded px-2 py-2"})


ParticularFormSet = formset_factory(ParticularLineForm, extra=8, can_delete=True)

