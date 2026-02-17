from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from org.models import Business
from mode_engine.models import ModeChoices


class RootType(models.TextChoices):
    ASSET = "ASSET", "Asset"
    LIABILITY = "LIABILITY", "Liability"
    INCOME = "INCOME", "Income"
    EXPENSE = "EXPENSE", "Expense"


class ReportType(models.TextChoices):
    BALANCE_SHEET = "BS", "Balance Sheet"
    PROFIT_LOSS = "PL", "Profit & Loss"


def report_type_from_root(root_type: str) -> str:
    if root_type in (RootType.INCOME, RootType.EXPENSE):
        return ReportType.PROFIT_LOSS
    return ReportType.BALANCE_SHEET


class Account(models.Model):
    """
    Tally mapping:
      - is_group=True  => Group
      - is_group=False => Ledger (posting allowed)
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")

    is_group = models.BooleanField(default=True)

    root_type = models.CharField(max_length=16, choices=RootType.choices, blank=True)
    report_type = models.CharField(max_length=2, choices=ReportType.choices, editable=False)

    # Optional but useful later (Bank/Cash/Receivable/Payable/etc.)
    account_type = models.CharField(max_length=64, blank=True, default="")

    # Optional: lock root nodes like Tally "Primary"
    is_root = models.BooleanField(default=False, editable=False)

    # Exception: one ledger with no group (e.g. Profit & Loss A/c) to store gross profit
    is_primary_ledger = models.BooleanField(default=False, blank=True)

    # Inventory and Opening Balance fields
    inventory_values_affected = models.BooleanField(default=False, blank=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), blank=True, null=True)
    opening_balance_type = models.CharField(
        max_length=2,
        choices=[("DR", "Dr"), ("CR", "Cr")],
        blank=True,
        default="DR",
    )
    opening_balance_date = models.DateField(null=True, blank=True)

    # Mailing & Related Details
    mailing_name = models.CharField(max_length=255, blank=True, default="")
    mailing_address = models.TextField(blank=True, default="")
    mailing_state = models.CharField(max_length=100, blank=True, default="")
    mailing_pin_code = models.CharField(max_length=20, blank=True, default="")
    income_tax_no = models.CharField(max_length=50, blank=True, default="")
    sales_tax_no = models.CharField(max_length=50, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "name"], name="uniq_account_name_per_business"),
        ]

    def __str__(self) -> str:
        return f"{self.name}"

    def clean(self):
        # Root accounts: parent must be null; usually must be group (exception: primary ledger)
        if self.parent is None:
            if self.is_group:
                # Root group: must have root_type
                if not self.root_type:
                    raise ValidationError({"root_type": "Root accounts must have a Nature of Group."})
                self.report_type = report_type_from_root(self.root_type)
            else:
                # Ledger with no parent: only allowed for primary ledger (e.g. Profit & Loss A/c)
                if not self.is_primary_ledger:
                    raise ValidationError({"is_group": "Root account must be a Group (is_group=True), unless it is a primary ledger."})
                self.report_type = ReportType.PROFIT_LOSS
        else:
            # Parent must be group
            if not self.parent.is_group:
                raise ValidationError({"parent": "Parent must be a Group account."})

            # Must belong to same business. For new instances, business may not be set yet
            # (form has no business field; view sets it before save). Use parent's business
            # when ours is None so the check passes and the view's assignment is consistent.
            my_business_id = self.business_id
            if my_business_id is None and self.parent_id:
                my_business_id = self.parent.business_id
                self.business_id = my_business_id
            if self.parent.business_id is not None and my_business_id != self.parent.business_id:
                raise ValidationError({"parent": "Parent must be in the same business."})

            # Inherit root/report types from parent (Tally-style)
            # This happens even if root_type was provided - parent takes precedence
            self.root_type = self.parent.root_type
            self.report_type = self.parent.report_type

        # Prevent changing root nodes later (simple version)
        if self.pk:
            old = Account.objects.filter(pk=self.pk).values("parent_id", "is_root").first()
            if old and old["is_root"]:
                raise ValidationError("Root accounts cannot be altered.")

    def save(self, *args, **kwargs):
        # Root = no parent and is a group (primary ledgers have no parent but are not "root" for locking)
        self.is_root = self.parent_id is None and self.is_group
        self.full_clean()
        return super().save(*args, **kwargs)


class VoucherType(models.TextChoices):
    RECEIPT = "RECEIPT", "Receipt"
    PAYMENT = "PAYMENT", "Payment"
    JOURNAL = "JOURNAL", "Journal"
    CONTRA = "CONTRA", "Contra"
    SALES = "SALES", "Sales"
    PURCHASE = "PURCHASE", "Purchase"


class Voucher(models.Model):
    """
    A voucher is an "event". It has lines. Posting locks it.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="vouchers")
    number = models.CharField(max_length=32)  # you can generate per-business later
    voucher_type = models.CharField(max_length=16, choices=VoucherType.choices)
    mode = models.CharField(max_length=16, choices=ModeChoices.choices, default=ModeChoices.BUSINESS)
    posting_date = models.DateField(default=timezone.localdate)
    narration = models.TextField(blank=True, default="")

    is_posted = models.BooleanField(default=False, editable=False)
    posted_at = models.DateTimeField(null=True, blank=True, editable=False)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, editable=False
    )

    # Optional: for linking to source documents
    source_type = models.CharField(max_length=64, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")
    business_source = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "number"], name="uniq_voucher_number_per_business"),
        ]

    def __str__(self) -> str:
        return f"{self.voucher_type} {self.number}"

    def clean(self):
        if self.is_posted and self.pk:
            # Don't allow edits on posted vouchers (simple safety)
            old = Voucher.objects.filter(pk=self.pk).values("is_posted").first()
            if old and old["is_posted"]:
                raise ValidationError("Posted vouchers are locked.")

    def _totals(self) -> tuple[Decimal, Decimal]:
        agg = self.lines.aggregate(
            dr=Sum("debit", default=Decimal("0.00")),
            cr=Sum("credit", default=Decimal("0.00")),
        )
        return (agg["dr"] or Decimal("0.00"), agg["cr"] or Decimal("0.00"))

    def validate_balanced(self):
        # Must have at least 2 lines
        if self.lines.count() < 2:
            raise ValidationError("Voucher must have at least two lines.")

        dr, cr = self._totals()
        if dr != cr:
            raise ValidationError(f"Voucher not balanced: Debit {dr} != Credit {cr}")

        # No posting to groups
        bad = self.lines.filter(account__is_group=True).exists()
        if bad:
            raise ValidationError("Cannot post to a Group. Post only to Ledger accounts (is_group=False).")

    @transaction.atomic
    def post(self, user=None):
        """
        Tally-like 'Submit': enforce rules, then lock.
        """
        if self.is_posted:
            return  # idempotent

        self.validate_balanced()

        self.is_posted = True
        self.posted_at = timezone.now()
        self.posted_by = user
        self.save()


class VoucherLine(models.Model):
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="voucher_lines")

    # Using separate debit/credit keeps it easy for beginners
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    memo = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            # one side only; allow zero while drafting, but not both > 0
            models.CheckConstraint(
                check=~(Q(debit__gt=0) & Q(credit__gt=0)),
                name="chk_not_both_debit_and_credit",
            ),
            models.CheckConstraint(
                check=Q(debit__gte=0) & Q(credit__gte=0),
                name="chk_debit_credit_non_negative",
            ),
        ]

    def clean(self):
        if self.voucher_id and self.voucher.is_posted:
            raise ValidationError("Cannot edit lines of a posted voucher.")

        if self.account_id and self.account.is_group:
            raise ValidationError({"account": "Cannot post to a Group. Choose a Ledger (is_group=False)."})

        if self.debit == Decimal("0.00") and self.credit == Decimal("0.00"):
            raise ValidationError("Line must have a debit or credit amount.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
