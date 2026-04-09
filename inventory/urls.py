from django.urls import path, reverse_lazy
from django.views.generic import RedirectView
from . import views

app_name = "inventory"

urlpatterns = [
    path("", RedirectView.as_view(url=reverse_lazy("reports:home")), name="gateway"),
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
    path("reports/stock-analysis/", views.stock_analysis, name="stock_analysis"),
    path("reports/stock-analysis/main/<int:pk>/", views.stock_analysis_sub_groups, name="stock_analysis_sub_groups"),
    path("reports/stock-analysis/sub/<int:pk>/", views.stock_analysis_items, name="stock_analysis_items"),
    path("reports/stock-analysis/item/<int:pk>/", views.stock_analysis_item_movement, name="stock_analysis_item_movement"),
    path("reports/stock-summary/sub-group/<int:pk>/", views.stock_summary_sub_group, name="stock_summary_sub_group"),
    # Legacy / full inventory (Stock Groups, Stock Items, Units)
    path("stock-groups/", views.stock_groups_display, name="stock_groups_gateway"),
    path("stock-groups/create/", views.stock_group_create, name="stock_group_create"),
    path("stock-groups/display/", views.stock_groups_display, name="stock_groups_display"),
    path("stock-groups/main/", views.stock_main_groups_display, name="stock_main_groups_display"),
    path("stock-groups/sub/", views.stock_sub_groups_display, name="stock_sub_groups_display"),
    path("stock-groups/<int:pk>/", views.stock_group_display, name="stock_group_display"),
    path("stock-groups/<int:pk>/alter/", views.stock_group_alter, name="stock_group_alter"),
    path("stock-groups/<int:pk>/delete/", views.stock_group_delete, name="stock_group_delete"),
    path("stock-items/", views.stock_items_display, name="stock_items_gateway"),
    path("stock-items/create/", views.stock_item_create, name="stock_item_create"),
    path("stock-items/display/", views.stock_items_display, name="stock_items_display"),
    path("stock-items/<int:pk>/", views.stock_item_display, name="stock_item_display"),
    path("stock-items/<int:pk>/alter/", views.stock_item_alter, name="stock_item_alter"),
    path("stock-items/<int:pk>/delete/", views.stock_item_delete, name="stock_item_delete"),
    path("stock-items/<int:pk>/standard-rates/", views.standard_rates, name="standard_rates"),
    path("units/", views.units_display, name="units_gateway"),
    path("units/create/", views.unit_create, name="unit_create"),
    path("units/display/", views.units_display, name="units_display"),
    path("units/<int:pk>/", views.unit_display, name="unit_display"),
    path("units/<int:pk>/alter/", views.unit_alter, name="unit_alter"),
    path("units/<int:pk>/delete/", views.unit_delete, name="unit_delete"),
]
