"""A7: dashboard and reports; A8: audit logs and system settings."""

import csv
from datetime import timedelta
from io import StringIO

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import (
    AuditLog,
    BorrowRequest,
    CatalogItem,
    Category,
    EquipmentUnit,
    Loan,
    RequestItem,
    SystemSetting,
    UnitAllocation,
)
from .helpers import (
    add_item,
    make_admin,
    make_item,
    make_request,
    make_unit,
    make_user,
    reserve,
)


class DashboardAndSettingsTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.borrower = make_user("borrower")
        self.client.force_login(self.admin)

        self.category = Category.objects.create(name="Laptops")
        self.item = CatalogItem.objects.create(
            category=self.category,
            name="Laptop",
        )
        self.unit = make_unit(
            self.item,
            asset_code="LAP-001",
            status=EquipmentUnit.ISSUED,
        )
        self.borrow_request = make_request(
            self.borrower,
            status=BorrowRequest.ISSUED,
            days=2,
            purpose="Classroom use",
        )
        request_item = add_item(self.borrow_request, self.item)
        UnitAllocation.objects.create(request_item=request_item, unit=self.unit)
        self.loan = Loan.objects.create(
            request=self.borrow_request,
            issued_by=self.admin,
        )

    def test_dashboard_uses_live_counts_and_issued_usage(self):
        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["available_units"], 0)
        self.assertEqual(response.context["active_loans"], 1)
        self.assertEqual(response.context["monthly_issued"][0]["count"], 1)
        self.assertEqual(response.context["category_usage"][0]["count"], 1)

    def test_dashboard_excludes_archived_inventory_from_available_count(self):
        archived_item = make_item("Old Projector")
        archived_item.is_archived = True
        archived_item.save(update_fields=["is_archived"])
        make_unit(archived_item, asset_code="ARC-001")

        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.context["available_units"], 0)

    def test_csv_report_contains_allocated_units_and_applies_date_filter(self):
        response = self.client.get(reverse("dashboard_report_csv"))

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        self.assertEqual(rows[1][-1], "LAP-001")

        future_date = (timezone.localdate() + timedelta(days=1)).isoformat()
        filtered_response = self.client.get(
            reverse("dashboard_report_csv"),
            {"date_from": future_date},
        )
        filtered_rows = list(
            csv.reader(StringIO(filtered_response.content.decode("utf-8")))
        )
        self.assertEqual(len(filtered_rows), 1)

    def test_csv_report_rejects_invalid_date_range(self):
        response = self.client.get(
            reverse("dashboard_report_csv"),
            {"date_from": "not-a-date"},
        )

        self.assertEqual(response.status_code, 400)

    def test_csv_export_is_audited(self):
        self.client.get(reverse("dashboard_report_csv"))

        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action="REPORT_EXPORTED",
            ).exists()
        )

    def test_settings_are_saved_and_audited(self):
        response = self.client.post(
            reverse("audit_settings_management"),
            {
                "max_loan_duration_days": "14",
                "max_quantity": "3",
            },
        )

        self.assertRedirects(response, reverse("audit_settings_management"))
        self.assertEqual(
            SystemSetting.objects.get(key="max_loan_duration_days").value,
            "14",
        )
        self.assertEqual(SystemSetting.objects.get(key="max_quantity").value, "3")
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action="SYSTEM_SETTINGS_UPDATED",
            ).exists()
        )

    def test_settings_reject_non_numeric_values(self):
        response = self.client.post(
            reverse("audit_settings_management"),
            {
                "max_loan_duration_days": "seven",
                "max_quantity": "3",
            },
        )

        self.assertRedirects(response, reverse("audit_settings_management"))
        self.assertFalse(
            SystemSetting.objects.filter(key="max_loan_duration_days").exists()
        )

    def test_settings_reject_out_of_range_values(self):
        self.client.post(
            reverse("audit_settings_management"),
            {
                "max_loan_duration_days": "0",
                "max_quantity": "3",
            },
        )

        self.assertFalse(
            SystemSetting.objects.filter(key="max_loan_duration_days").exists()
        )

    def test_settings_page_and_report_require_admin_role(self):
        basic_user = make_user("basic")

        self.client.force_login(basic_user)
        self.assertEqual(
            self.client.get(reverse("audit_settings_management")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("dashboard_report_csv")).status_code,
            403,
        )

    def test_request_approval_obeys_configured_max_quantity(self):
        SystemSetting.objects.create(key="max_quantity", value="1")
        pending_request = make_request(self.borrower, purpose="Two items")
        RequestItem.objects.create(
            request=pending_request,
            catalog_item=self.item,
            quantity=2,
        )

        response = self.client.post(
            reverse("request_approve", args=[pending_request.pk]),
        )

        self.assertRedirects(response, reverse("request_review"))
        pending_request.refresh_from_db()
        self.assertEqual(pending_request.status, BorrowRequest.PENDING)

    def test_issuing_obeys_configured_max_loan_duration(self):
        SystemSetting.objects.create(key="max_loan_duration_days", value="1")
        approved_request = make_request(
            self.borrower,
            status=BorrowRequest.APPROVED,
            days=2,
            purpose="Long loan",
        )
        request_item = add_item(approved_request, self.item)
        reserved_unit = make_unit(self.item, asset_code="LAP-002")
        reserve(request_item, reserved_unit)

        response = self.client.post(
            reverse("issue_approved_request", args=[approved_request.pk]),
        )

        self.assertRedirects(response, reverse("release_management"))
        approved_request.refresh_from_db()
        self.assertEqual(approved_request.status, BorrowRequest.APPROVED)
        self.assertFalse(Loan.objects.filter(request=approved_request).exists())


class OverdueReportTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.borrower = make_user("borrower")
        self.item = make_item()
        self.unit = make_unit(
            self.item,
            asset_code="OVD-001",
            status=EquipmentUnit.ISSUED,
        )
        self.overdue_request = make_request(
            self.borrower,
            status=BorrowRequest.ISSUED,
            days=-3,
            purpose="Overdue loan",
        )
        request_item = add_item(self.overdue_request, self.item)
        UnitAllocation.objects.create(
            request_item=request_item,
            unit=self.unit,
        )
        self.loan = Loan.objects.create(
            request=self.overdue_request,
            issued_by=self.admin,
        )
        self.client.force_login(self.admin)

    def test_overdue_report_lists_outstanding_units_and_days(self):
        response = self.client.get(reverse("overdue_report"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 1)
        self.assertEqual(response.context["rows"][0]["overdue_days"], 3)
        self.assertContains(response, "OVD-001")
        self.assertContains(response, "3 day(s)")

    def test_overdue_report_excludes_loans_not_yet_due(self):
        current_request = make_request(
            self.borrower,
            status=BorrowRequest.ISSUED,
            days=2,
            purpose="Not due yet",
        )
        request_item = add_item(current_request, self.item)
        current_unit = make_unit(
            self.item,
            asset_code="CUR-001",
            status=EquipmentUnit.ISSUED,
        )
        UnitAllocation.objects.create(
            request_item=request_item,
            unit=current_unit,
        )
        Loan.objects.create(request=current_request, issued_by=self.admin)

        response = self.client.get(reverse("overdue_report"))

        self.assertEqual(len(response.context["rows"]), 1)
        self.assertContains(response, "OVD-001")
        self.assertNotContains(response, "CUR-001")

    def test_overdue_csv_exports_the_same_rows(self):
        response = self.client.get(reverse("overdue_report_csv"))

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        self.assertEqual(rows[1][0], str(self.loan.pk))
        self.assertEqual(rows[1][-2], "1")
        self.assertEqual(rows[1][-1], "OVD-001")
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action="REPORT_EXPORTED",
                details__contains="overdue",
            ).exists()
        )

    def test_overdue_reports_apply_date_range_and_validate_input(self):
        future_date = (timezone.localdate() + timedelta(days=1)).isoformat()

        filtered = self.client.get(
            reverse("overdue_report"),
            {"date_from": future_date},
        )
        self.assertEqual(filtered.context["rows"], [])

        invalid_csv = self.client.get(
            reverse("overdue_report_csv"),
            {"date_from": "not-a-date"},
        )
        self.assertEqual(invalid_csv.status_code, 400)

    def test_overdue_reports_require_admin_role(self):
        basic_user = make_user("basic")
        self.client.force_login(basic_user)

        self.assertEqual(
            self.client.get(reverse("overdue_report")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("overdue_report_csv")).status_code,
            403,
        )


class AuditLogTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_audit_log_can_be_searched(self):
        AuditLog.objects.create(
            actor=self.admin,
            action="CATEGORY_CREATED",
            details="Created category Robotics",
        )
        AuditLog.objects.create(
            actor=self.admin,
            action="ACCOUNT_ACTIVATED",
            details="Activated borrower",
        )

        response = self.client.get(
            reverse("audit_settings_management"),
            {"q": "Robotics"},
        )

        logs = response.context["page_obj"].object_list
        self.assertEqual([log.action for log in logs], ["CATEGORY_CREATED"])

    def test_audit_log_can_be_filtered_by_date(self):
        AuditLog.objects.create(
            actor=self.admin,
            action="CATEGORY_CREATED",
            details="Created category Robotics",
        )
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

        response = self.client.get(
            reverse("audit_settings_management"),
            {"date_from": tomorrow},
        )

        self.assertFalse(response.context["page_obj"].object_list)

    def test_invalid_audit_date_range_is_rejected(self):
        today = timezone.localdate().isoformat()
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()

        response = self.client.get(
            reverse("audit_settings_management"),
            {"date_from": today, "date_to": yesterday},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_from"], "")
        self.assertEqual(response.context["date_to"], "")
