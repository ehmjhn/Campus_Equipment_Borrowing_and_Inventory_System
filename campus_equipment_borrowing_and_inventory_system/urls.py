from django.urls import path, include
from django.shortcuts import redirect
from Campus_Equipment_Borrowing_and_Inventory_System_APP import views

urlpatterns = [
    # Home
    path("", lambda request: redirect("admin_dashboard"), name="home"),

    # Dashboard and reports
    path("manage/", views.admin_dashboard, name="admin_dashboard"),
    path("manage/reports/equipment-usage.csv", views.dashboard_report_csv, name="dashboard_report_csv"),

    # A1 - Account Management
    path("manage/accounts/", views.account_management, name="account_management"),
    path("manage/accounts/<int:user_id>/toggle-status/", views.toggle_account_status, name="toggle_account_status"),
    path("accounts/", include("django.contrib.auth.urls")),

    # A2 - Equipment Catalog
    path("manage/categories/", views.category_management, name="category_management"),
    path("manage/categories/create/", views.category_create, name="category_create"),
    path("manage/categories/<int:category_id>/edit/", views.category_edit, name="category_edit"),
    path("manage/categories/<int:category_id>/archive/", views.category_archive, name="category_archive"),
    path("manage/catalog-items/", views.catalog_item_management, name="catalog_item_management"),
    path("manage/catalog-items/create/", views.catalog_item_create, name="catalog_item_create"),
    path("manage/catalog-items/<int:item_id>/edit/", views.catalog_item_edit, name="catalog_item_edit"),
    path("manage/catalog-items/<int:item_id>/archive/", views.catalog_item_archive, name="catalog_item_archive"),
    path("manage/equipment-units/create/", views.equipment_unit_create, name="equipment_unit_create"),
    path("manage/physical-units/", views.physical_units_management, name="physical_units_management"),

    # A3 - Request Review
    path("manage/requests/", views.request_review, name="request_review"),
    path("manage/requests/<int:request_id>/approve/", views.request_approve, name="request_approve"),
    path("manage/requests/<int:request_id>/reject/", views.request_reject, name="request_reject"),

    # A4 - Release and Borrowing Slips
    path("manage/releases/", views.release_management, name="release_management"),
    path("manage/releases/<int:request_id>/issue/", views.issue_approved_request, name="issue_approved_request"),
    path("manage/releases/<int:request_id>/revise-due-date/", views.revise_approved_due_date, name="revise_approved_due_date"),
    path("manage/releases/<int:request_id>/slip/", views.borrowing_slip, name="borrowing_slip"),

    # A5 - Returns and Overdue Loans
    path("manage/returns/", views.return_management, name="return_management"),
    path("manage/returns/<int:loan_id>/<int:unit_id>/record/", views.record_unit_return, name="record_unit_return"),

    # A6 - Maintenance
    path("manage/maintenance/", views.maintenance_management, name="maintenance_management"),
    path("manage/maintenance/create/", views.open_maintenance_record, name="open_maintenance_record"),
    path("manage/maintenance/<int:record_id>/close/", views.close_maintenance_record, name="close_maintenance_record"),

    # A8 - Audit Logs and System Settings
    path("manage/audit-settings/", views.audit_settings_management, name="audit_settings_management"),

    # U1 - Account and profile
    path("portal/profile/", views.profile_view, name="profile_view"),

    # U2 - Browse equipment
    path("portal/catalog/", views.browse_catalog, name="browse_catalog"),
]