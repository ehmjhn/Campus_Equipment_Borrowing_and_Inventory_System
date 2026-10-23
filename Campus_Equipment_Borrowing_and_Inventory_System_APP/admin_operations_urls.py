from django.urls import path

from . import admin_operations


urlpatterns = [
    path(
        "manage/audit-settings/",
        admin_operations.audit_settings_management,
        name="audit_settings_management",
    ),
    path("manage/releases/", admin_operations.release_management, name="release_management"),
    path("manage/releases/<int:request_id>/issue/", admin_operations.issue_approved_request, name="issue_approved_request"),
    path("manage/releases/<int:request_id>/revise-due-date/", admin_operations.revise_approved_due_date, name="revise_approved_due_date"),
    path("manage/releases/<int:request_id>/slip/", admin_operations.borrowing_slip, name="borrowing_slip"),
    path("manage/returns/", admin_operations.return_management, name="return_management"),
    path("manage/returns/<int:loan_id>/<int:unit_id>/record/", admin_operations.record_unit_return, name="record_unit_return"),
    path("manage/maintenance/", admin_operations.maintenance_management, name="maintenance_management"),
    path("manage/maintenance/create/", admin_operations.open_maintenance_record, name="open_maintenance_record"),
    path("manage/maintenance/<int:record_id>/close/", admin_operations.close_maintenance_record, name="close_maintenance_record"),
]
