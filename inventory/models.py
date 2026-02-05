from django.db import models
from org.models import Business
from mode_engine.models import ModeChoices


class StockGroup(models.Model):
    """Tally-style stock group. parent=None means 'Primary' (root)."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="stock_groups")
    name = models.CharField(max_length=255)
    alias = models.CharField(max_length=255, blank=True, default="")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    can_quantities_be_added = models.BooleanField(
        default=True,
        help_text="Can quantities of items be ADDED?",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "name"], name="inventory_stockgroup_business_name_uniq"
            ),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class UnitOfMeasure(models.Model):
    """Unit of measure (e.g. pcs, kg). Type=Simple for basic units."""
    TYPE_CHOICES = [("SIMPLE", "Simple"), ("COMPOUND", "Compound")]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="units_of_measure")
    unit_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default="SIMPLE")
    symbol = models.CharField(max_length=32)
    formal_name = models.CharField(max_length=100, blank=True, default="")
    decimal_places = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "symbol"], name="inventory_unit_business_symbol_uniq"
            ),
        ]

    def __str__(self):
        return self.symbol or self.formal_name or str(self.pk)


class Item(models.Model):
    """Stock Item master (Tally: Stock Items)."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=200, blank=True, default="")
    alias = models.CharField(max_length=200, blank=True, default="")
    stock_group = models.ForeignKey(
        StockGroup, null=True, blank=True, on_delete=models.PROTECT, related_name="items"
    )
    unit = models.ForeignKey(
        UnitOfMeasure, null=True, blank=True, on_delete=models.SET_NULL, related_name="items"
    )
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_stock_item = models.BooleanField(default=True)

    class Meta:
        unique_together = ("business", "sku")

    def __str__(self):
        return self.sku or self.alias or str(self.pk)


class StandardRate(models.Model):
    """Standard cost or selling price for an item, effective from a date."""
    RATE_TYPES = [("COST", "Cost"), ("SELLING", "Selling")]
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="standard_rates")
    rate_type = models.CharField(max_length=16, choices=RATE_TYPES)
    applicable_from = models.DateField()
    rate = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["-applicable_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "rate_type", "applicable_from"],
                name="inventory_standardrate_item_type_date_uniq",
            ),
        ]


class Godown(models.Model):
    """Godown (Tally term for warehouse). Balances derived from StockLedgerEntry, never stored."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="godowns")
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "name"], name="inventory_warehouse_business_name_uniq"
            ),
        ]

    def __str__(self):
        return self.name


class StockLedgerEntry(models.Model):
    """
    Internal movement table (not shown in UI). Tally-style: balances = sum(qty_in)-sum(qty_out).
    voucher_type: PURCHASE, SALES, STOCK_JOURNAL.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="stock_ledger_entries")
    posting_date = models.DateField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="stock_ledger_entries")
    godown = models.ForeignKey(Godown, on_delete=models.PROTECT, related_name="stock_ledger_entries")
    qty_in = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    qty_out = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    rate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    voucher_type = models.CharField(max_length=64, blank=True, default="")
    voucher_id = models.IntegerField(null=True, blank=True)
    is_posted = models.BooleanField(default=False)
    narration = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-posting_date", "-id"]
        verbose_name_plural = "Stock ledger entries"


class StockMovement(models.Model):
    MOVEMENT_TYPES = [("OPENING","Opening"),("PURCHASE","Purchase"),("SALE","Sale"),("ADJUST","Adjust")]
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    mode = models.CharField(max_length=16, choices=ModeChoices.choices, default=ModeChoices.BUSINESS)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    qty_delta = models.DecimalField(max_digits=12, decimal_places=2)
    movement_type = models.CharField(max_length=16, choices=MOVEMENT_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
