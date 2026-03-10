from django.urls import path
from .views import balance_sheet, cash_bank_summary, day_book, home, pnl, profit_and_loss, reports_list

app_name = "reports"

urlpatterns = [
    path("", home, name="home"),
    path("list/", reports_list, name="reports_list"),
    path("pnl/", pnl, name="pnl"),
    path("profit-and-loss/", profit_and_loss, name="profit_and_loss"),
    path("balance-sheet/", balance_sheet, name="balance_sheet"),
    path("cash-bank-summary/", cash_bank_summary, name="cash_bank_summary"),
    path("day-book/", day_book, name="day_book"),
]
