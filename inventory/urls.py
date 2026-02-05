from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.gateway, name="gateway"),
    path("balance/", views.balance_view, name="balance"),
    # Tally-style: Masters, Vouchers, Reports
    path("items/", views.items_list, name="items_list"),
    path("items/new/", views.item_create, name="item_create"),
    path("items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path("godowns/", views.godowns_list, name="godowns_list"),
    path("godowns/new/", views.godown_create, name="godown_create"),
    path("godowns/<int:pk>/edit/", views.godown_edit, name="godown_edit"),
    path("vouchers/purchase/", views.purchase_voucher_create, name="purchase_voucher_create"),
    path("vouchers/sales/", views.sales_voucher, name="sales_voucher"),
    path("vouchers/stock-journal/", views.stock_journal, name="stock_journal"),
    path("reports/stock-summary/", views.stock_summary, name="stock_summary"),
    # Legacy / full inventory (Stock Groups, Stock Items, Units)
    path("stock-groups/", views.stock_groups_gateway, name="stock_groups_gateway"),
    path("stock-groups/create/", views.stock_group_create, name="stock_group_create"),
    path("stock-groups/display/", views.stock_groups_display, name="stock_groups_display"),
    path("stock-groups/<int:pk>/alter/", views.stock_group_alter, name="stock_group_alter"),
    path("stock-items/", views.stock_items_gateway, name="stock_items_gateway"),
    path("stock-items/create/", views.stock_item_create, name="stock_item_create"),
    path("stock-items/display/", views.stock_items_display, name="stock_items_display"),
    path("stock-items/<int:pk>/alter/", views.stock_item_alter, name="stock_item_alter"),
    path("stock-items/<int:pk>/standard-rates/", views.standard_rates, name="standard_rates"),
    path("units/", views.units_gateway, name="units_gateway"),
    path("units/create/", views.unit_create, name="unit_create"),
    path("units/display/", views.units_display, name="units_display"),
    path("units/<int:pk>/alter/", views.unit_alter, name="unit_alter"),
]
