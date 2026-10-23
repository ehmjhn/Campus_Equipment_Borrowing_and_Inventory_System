import csv
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AuditLog,
    BorrowRequest,
    CatalogItem,
    Category,
    EquipmentUnit,
    Loan,
    RequestItem,
    SystemSetting,
    UnitAllocation,
    UserProfile,
)


class AdminDashboardAndSettingsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin",
            password="test-password",
        )
        UserProfile.objects.create(user=self.admin, role=UserProfile.ADMIN)
        self.client.force_login(self.admin)

        self.category = Category.objects.create(name="Laptops")
        self.item = CatalogItem.objects.create(
            category=self.category,
            name="Laptop",
        )
        self.unit = EquipmentUnit.objects.create(
            catalog_item=self.item,
            asset_code="LAP-001",
            condition="Good",
            acquisition_date=timezone.localdate(),
            status=EquipmentUnit.ISSUED,
        )
        self.borrow_request = BorrowRequest.objects.create(
            user=self.admin,
            purpose="Classroom use",
            return_date=timezone.localdate() + timedelta(days=2),
            status=BorrowRequest.ISSUED,
        )
        request_item = RequestItem.objects.create(
            request=self.borrow_request,
            catalog_item=self.item,
            quantity=1,
        )
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

    def test_settings_page_and_report_require_admin_role(self):
        basic_user = User.objects.create_user(
            username="borrower",
            password="test-password",
        )
        UserProfile.objects.create(user=basic_user)

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
        pending_request = BorrowRequest.objects.create(
            user=self.admin,
            purpose="Two items",
            return_date=timezone.localdate() + timedelta(days=2),
        )
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
        approved_request = BorrowRequest.objects.create(
            user=self.admin,
            purpose="Long loan",
            return_date=timezone.localdate() + timedelta(days=2),
            status=BorrowRequest.APPROVED,
        )
        request_item = RequestItem.objects.create(
            request=approved_request,
            catalog_item=self.item,
            quantity=1,
        )
        UnitAllocation.objects.create(request_item=request_item, unit=self.unit)
        self.unit.status = EquipmentUnit.RESERVED
        self.unit.save(update_fields=["status"])

        response = self.client.post(
            reverse("issue_approved_request", args=[approved_request.pk]),
        )

        self.assertRedirects(response, reverse("release_management"))
        approved_request.refresh_from_db()
        self.assertEqual(approved_request.status, BorrowRequest.APPROVED)
        self.assertFalse(Loan.objects.filter(request=approved_request).exists())
