from django.db import models

class ModeChoices(models.TextChoices):
    BUSINESS = "BUSINESS", "Business"
    LEGAL = "LEGAL", "Legal"
