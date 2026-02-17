from django.urls import path
from . import views

app_name = "ledger"

urlpatterns = [
    path("", views.gateway, name="gateway"),

    # Accounts Gateway (Tally-style)
    path("accounts/", views.accounts_gateway, name="accounts_gateway"),
    
    # Groups
    path("accounts/groups/create/", views.group_create, name="group_create"),
    path("accounts/groups/display/", views.groups_display, name="groups_display"),
    path("accounts/groups/<int:pk>/alter/", views.group_alter, name="group_alter"),
    path("accounts/groups/<int:pk>/summary/", views.group_summary, name="group_summary"),

    # Ledgers
    path("accounts/ledgers/create/", views.ledger_create, name="ledger_create"),
    path("accounts/ledgers/display/", views.ledgers_display, name="ledgers_display"),
    path("accounts/ledgers/<int:pk>/alter/", views.ledger_alter, name="ledger_alter"),
    path("accounts/ledgers/<int:pk>/voucher-details/", views.ledger_voucher_details, name="ledger_voucher_details"),
    
    # Voucher Types
    path("accounts/voucher-types/create/", views.voucher_type_create, name="voucher_type_create"),
    path("accounts/voucher-types/display/", views.voucher_types_display, name="voucher_types_display"),
    path("accounts/voucher-types/<int:pk>/alter/", views.voucher_type_alter, name="voucher_type_alter"),

    # Vouchers
    path("vouchers/", views.voucher_list, name="voucher_list"),
    path("vouchers/entry/<str:vtype>/", views.voucher_entry, name="voucher_entry"),
    path("vouchers/new/", views.voucher_create, name="voucher_create"),
    path("vouchers/<int:pk>/", views.voucher_detail, name="voucher_detail"),
    path("vouchers/<int:pk>/edit/", views.voucher_edit, name="voucher_edit"),
    path("vouchers/<int:pk>/post/", views.voucher_post, name="voucher_post"),
    path("vouchers/<int:pk>/delete/", views.voucher_delete, name="voucher_delete"),

    # COA installer
    path("coa/install/", views.install_coa, name="install_coa"),

    # API (Cur Bal Dr/Cr)
    path("api/account-balance/<int:account_id>/", views.api_account_balance, name="api_account_balance"),
]
