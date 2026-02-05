from django.db import models
from org.models import Business
from mode_engine.models import ModeChoices

class Invoice(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    mode = models.CharField(max_length=16, choices=ModeChoices.choices, default=ModeChoices.BUSINESS)
    locked = models.BooleanField(default=False)
    business_source = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    invoice_no = models.CharField(max_length=64)
    date = models.DateField()
    customer_name = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = ("business", "mode", "invoice_no")

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
