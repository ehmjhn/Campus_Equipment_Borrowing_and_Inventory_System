from django.urls import path, include
from Campus_Equipment_Borrowing_and_Inventory_System_APP import views

urlpatterns = [
    # Home and post-login routing (role aware)
    path("", views.role_redirect, name="home"),
    path("dashboard/", views.role_redirect, name="post_login"),

    # Dashboard and reports
    path("manage/", views.admin_dashboard, name="admin_dashboard"),
    path("manage/reports/equipment-usage.csv", views.dashboard_report_csv, name="dashboard_report_csv"),
    path("manage/reports/overdue/", views.overdue_report, name="overdue_report"),
    path("manage/reports/overdue.csv", views.overdue_report_csv, name="overdue_report_csv"),

    # A1 - Account Management
    path("manage/accounts/", views.account_management, name="account_management"),
    path("manage/accounts/<int:user_id>/", views.account_detail, name="account_detail"),
    path("manage/accounts/<int:user_id>/toggle-status/", views.toggle_account_status, name="toggle_account_status"),
    path("accounts/register/", views.register, name="register"),
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
    path("manage/equipment-units/<int:unit_id>/update/", views.equipment_unit_update, name="equipment_unit_update"),
    path("manage/equipment-units/<int:unit_id>/retire/", views.equipment_unit_retire, name="equipment_unit_retire"),
    path("manage/equipment-units/<int:unit_id>/restore/", views.equipment_unit_restore, name="equipment_unit_restore"),
    path("manage/physical-units/", views.physical_units_management, name="physical_units_management"),
    path("manage/physical-units/reconcile/", views.reconcile_inventory, name="reconcile_inventory"),

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
    path("portal/", views.portal_home, name="portal_home"),
    path("portal/profile/", views.profile_view, name="profile_view"),
    path("portal/profile/change-password/", views.password_change_view, name="password_change"),

    # U2 - Browse equipment
    path("portal/catalog/", views.browse_catalog, name="browse_catalog"),

    # U3 - Submit borrowing requests
    path("portal/requests/new/", views.borrow_request_create, name="borrow_request_create"),

    # U4 - Track and cancel borrowing requests
    path("portal/requests/", views.request_history, name="request_history"),
    path(
        "portal/requests/<int:request_id>/cancel/",
        views.cancel_borrow_request,
        name="cancel_borrow_request",
    ),
]