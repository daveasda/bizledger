from django.contrib import admin
from .models import Item, StockMovement, Godown, StockLedgerEntry

admin.site.register(Item)
admin.site.register(StockMovement)
admin.site.register(Godown)
admin.site.register(StockLedgerEntry)
