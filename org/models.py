from django.conf import settings
from django.db import models

class Business(models.Model):
    BUSINESS_TYPES = [
        ("SERVICE_STATION", "Service Station"),
        ("IMPORT", "Importing"),
        ("RETAIL", "Retail"),
    ]
    name = models.CharField(max_length=200)
    business_type = models.CharField(max_length=30, choices=BUSINESS_TYPES, default="RETAIL")

    def __str__(self):
        return self.name

class Membership(models.Model):
    ROLE_CHOICES = [
        ("OWNER", "Owner"),
        ("MANAGER", "Manager"),
        ("CASHIER", "Cashier"),
        ("ACCOUNTANT", "Accountant"),
        ("LEGAL", "Legal"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="MANAGER")

    class Meta:
        unique_together = ("user", "business")
