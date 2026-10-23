from django.urls import path, include
from django.shortcuts import redirect

from Campus_Equipment_Borrowing_and_Inventory_System_APP import views


urlpatterns = [
    path(
        "",
        lambda request: redirect("admin_dashboard"),
        name="home",
    ),
    path(
        "manage/",
        views.admin_dashboard,
        name="admin_dashboard",
    ),
    path(
        "manage/reports/equipment-usage.csv",
        views.dashboard_report_csv,
        name="dashboard_report_csv",
    ),
    path(
        "manage/accounts/",
        views.account_management,
        name="account_management",
    ),
    path(
        "manage/accounts/<int:user_id>/toggle-status/",
        views.toggle_account_status,
        name="toggle_account_status",
    ),
    path(
        "accounts/",
        include("django.contrib.auth.urls"),
    ),

    path(
        "manage/categories/",
        views.category_management,
        name="category_management",
    ),
    path(
        "manage/categories/create/",
        views.category_create,
        name="category_create",
    ),
    path(
        "manage/categories/<int:category_id>/edit/",
        views.category_edit,
        name="category_edit",
    ),
    path(
        "manage/categories/<int:category_id>/archive/",
        views.category_archive,
        name="category_archive",
    ),
    path(
        "manage/catalog-items/",
        views.catalog_item_management,
        name="catalog_item_management",
    ),
    path(
        "manage/catalog-items/create/",
        views.catalog_item_create,
        name="catalog_item_create",
    ),
    path(
        "manage/catalog-items/<int:item_id>/edit/",
        views.catalog_item_edit,
        name="catalog_item_edit",
    ),
    path(
        "manage/catalog-items/<int:item_id>/archive/",
        views.catalog_item_archive,
        name="catalog_item_archive",
    ),
    path(
        "manage/equipment-units/create/",
        views.equipment_unit_create,
        name="equipment_unit_create",
    ),
    path(
        "manage/physical-units/",
        views.physical_units_management,
        name="physical_units_management",
    ),
    path(
        "manage/requests/",
        views.request_review,
        name="request_review",
    ),
    path(
        "manage/requests/<int:request_id>/approve/",
        views.request_approve,
        name="request_approve",
    ),
    path(
        "manage/requests/<int:request_id>/reject/",
        views.request_reject,
        name="request_reject",
    ),

    path(
        "",
        include(
            "Campus_Equipment_Borrowing_and_Inventory_System_APP.admin_operations_urls"
        ),
    ),

]
