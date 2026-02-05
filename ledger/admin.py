from django.contrib import admin
from .models import Account, Voucher, VoucherLine

admin.site.register(Account)
admin.site.register(Voucher)
admin.site.register(VoucherLine)
