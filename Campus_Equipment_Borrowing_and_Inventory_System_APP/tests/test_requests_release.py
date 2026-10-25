"""A3: request review (approve/reject) and A4: equipment release."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import (
    AuditLog,
    BorrowRequest,
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


class RequestReviewTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.borrower = make_user("borrower")
        self.item = make_item()
        self.client.force_login(self.admin)

    def test_approval_reserves_specific_units(self):
        borrow_request = make_request(self.borrower)
        add_item(borrow_request, self.item)
        unit = make_unit(self.item, asset_code="AST-001")

        response = self.client.post(
            reverse("request_approve", args=[borrow_request.pk]),
            {"admin_remarks": "Approved for class use."},
        )

        self.assertRedirects(response, reverse("request_review"))
        borrow_request.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.APPROVED)
        self.assertEqual(borrow_request.admin_remarks, "Approved for class use.")
        self.assertEqual(unit.status, EquipmentUnit.RESERVED)
        self.assertTrue(
            UnitAllocation.objects.filter(
                request_item__request=borrow_request,
                unit=unit,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="REQUEST_APPROVED").exists()
        )

    def test_approval_fails_when_stock_is_insufficient(self):
        borrow_request = make_request(self.borrower)
        add_item(borrow_request, self.item, quantity=2)
        make_unit(self.item, asset_code="AST-001")

        self.client.post(reverse("request_approve", args=[borrow_request.pk]))

        borrow_request.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.PENDING)
        self.assertFalse(UnitAllocation.objects.exists())

    def test_approval_respects_configured_max_quantity(self):
        SystemSetting.objects.create(key="max_quantity", value="1")
        borrow_request = make_request(self.borrower)
        add_item(borrow_request, self.item, quantity=2)
        make_unit(self.item, asset_code="AST-001")
        make_unit(self.item, asset_code="AST-002")

        self.client.post(reverse("request_approve", args=[borrow_request.pk]))

        borrow_request.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.PENDING)
        self.assertFalse(UnitAllocation.objects.exists())

    def test_unit_already_reserved_elsewhere_blocks_second_approval(self):
        first = make_request(self.borrower, purpose="First")
        first_item = add_item(first, self.item)
        unit = make_unit(self.item, asset_code="AST-001")
        reserve(first_item, unit)
        first.status = BorrowRequest.APPROVED
        first.save(update_fields=["status"])

        second = make_request(self.borrower, purpose="Second")
        add_item(second, self.item)

        self.client.post(reverse("request_approve", args=[second.pk]))

        second.refresh_from_db()
        self.assertEqual(second.status, BorrowRequest.PENDING)
        self.assertEqual(UnitAllocation.objects.count(), 1)

    def test_competing_approvals_for_last_unit_allow_only_one(self):
        first = make_request(self.borrower, purpose="First")
        add_item(first, self.item)
        second = make_request(self.borrower, purpose="Second")
        add_item(second, self.item)
        unit = make_unit(self.item, asset_code="AST-001")

        self.client.post(reverse("request_approve", args=[first.pk]))
        self.client.post(reverse("request_approve", args=[second.pk]))

        first.refresh_from_db()
        second.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(first.status, BorrowRequest.APPROVED)
        self.assertEqual(second.status, BorrowRequest.PENDING)
        self.assertEqual(unit.status, EquipmentUnit.RESERVED)
        self.assertEqual(
            UnitAllocation.objects.filter(released_at__isnull=True).count(),
            1,
        )

    def test_rejection_requires_a_reason(self):
        borrow_request = make_request(self.borrower)

        self.client.post(reverse("request_reject", args=[borrow_request.pk]))

        borrow_request.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.PENDING)

    def test_rejection_records_reason_and_audit(self):
        borrow_request = make_request(self.borrower)

        self.client.post(
            reverse("request_reject", args=[borrow_request.pk]),
            {"rejection_reason": "Equipment needed for a scheduled class."},
        )

        borrow_request.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.REJECTED)
        self.assertEqual(
            borrow_request.admin_remarks,
            "Equipment needed for a scheduled class.",
        )
        self.assertTrue(AuditLog.objects.filter(action="REQUEST_REJECTED").exists())

    def test_review_queue_shows_current_availability_for_each_item(self):
        borrow_request = make_request(self.borrower)
        add_item(borrow_request, self.item, quantity=2)
        make_unit(self.item, asset_code="AST-001")
        make_unit(self.item, asset_code="AST-002")
        make_unit(
            self.item,
            asset_code="AST-003",
            status=EquipmentUnit.ISSUED,
        )

        response = self.client.get(reverse("request_review"))

        self.assertContains(response, "Available now:</strong> 2")

    def test_review_queue_filters_by_requested_date(self):
        old_request = make_request(self.borrower, purpose="Old request")
        BorrowRequest.objects.filter(pk=old_request.pk).update(
            requested_at=timezone.now() - timedelta(days=10)
        )
        new_request = make_request(self.borrower, purpose="New request")

        response = self.client.get(
            reverse("request_review"),
            {"date_from": timezone.localdate().isoformat()},
        )

        returned_ids = [
            borrow_request.pk
            for borrow_request in response.context["requests"]
        ]
        self.assertIn(new_request.pk, returned_ids)
        self.assertNotIn(old_request.pk, returned_ids)

    def test_review_queue_is_searchable_and_paginated(self):
        for index in range(12):
            make_request(self.borrower, purpose=f"Purpose {index}")

        response = self.client.get(reverse("request_review"))
        self.assertEqual(response.context["page_obj"].paginator.per_page, 10)

        filtered = self.client.get(reverse("request_review"), {"q": "Purpose 11"})
        self.assertEqual(
            len(filtered.context["page_obj"].object_list),
            1,
        )


class ReleaseTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.borrower = make_user("borrower")
        self.item = make_item()
        self.client.force_login(self.admin)

        self.borrow_request = make_request(
            self.borrower,
            status=BorrowRequest.APPROVED,
            days=3,
        )
        self.request_item = add_item(self.borrow_request, self.item)
        self.unit = make_unit(self.item, asset_code="AST-001")
        reserve(self.request_item, self.unit)

    def test_issue_creates_loan_and_marks_units_issued(self):
        response = self.client.post(
            reverse("issue_approved_request", args=[self.borrow_request.pk])
        )

        self.assertRedirects(
            response,
            reverse("borrowing_slip", args=[self.borrow_request.pk]),
        )

        self.borrow_request.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.borrow_request.status, BorrowRequest.ISSUED)
        self.assertEqual(self.unit.status, EquipmentUnit.ISSUED)
        self.assertTrue(
            Loan.objects.filter(
                request=self.borrow_request,
                issued_by=self.admin,
            ).exists()
        )
        self.assertTrue(AuditLog.objects.filter(action="LOAN_ISSUED").exists())

    def test_request_cannot_be_issued_twice(self):
        Loan.objects.create(request=self.borrow_request, issued_by=self.admin)

        response = self.client.post(
            reverse("issue_approved_request", args=[self.borrow_request.pk])
        )

        self.assertRedirects(response, reverse("release_management"))
        self.assertEqual(Loan.objects.filter(request=self.borrow_request).count(), 1)

    def test_cancelled_request_cannot_be_issued(self):
        self.borrow_request.status = BorrowRequest.CANCELLED
        self.borrow_request.save(update_fields=["status"])

        self.client.post(
            reverse("issue_approved_request", args=[self.borrow_request.pk])
        )

        self.assertFalse(Loan.objects.filter(request=self.borrow_request).exists())

    def test_borrowing_slip_renders_allocated_assets(self):
        self.client.post(
            reverse("issue_approved_request", args=[self.borrow_request.pk])
        )

        response = self.client.get(
            reverse("borrowing_slip", args=[self.borrow_request.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AST-001")

    def test_returned_unit_can_be_allocated_to_a_new_request(self):
        self.client.post(
            reverse("issue_approved_request", args=[self.borrow_request.pk])
        )
        loan = Loan.objects.get(request=self.borrow_request)
        self.client.post(
            reverse("record_unit_return", args=[loan.pk, self.unit.pk]),
            {"condition_status": "Good"},
        )

        new_request = make_request(self.borrower, purpose="Borrow the unit again")
        add_item(new_request, self.item)
        self.client.post(reverse("request_approve", args=[new_request.pk]))

        new_request.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(new_request.status, BorrowRequest.APPROVED)
        self.assertEqual(self.unit.status, EquipmentUnit.RESERVED)
        self.assertEqual(
            UnitAllocation.objects.filter(
                unit=self.unit,
                released_at__isnull=True,
            ).count(),
            1,
        )
        self.assertEqual(
            UnitAllocation.objects.filter(unit=self.unit).count(),
            2,
        )

    def test_due_date_revision_is_validated_and_audited(self):
        new_due_date = (timezone.localdate() + timedelta(days=4)).isoformat()

        self.client.post(
            reverse("revise_approved_due_date", args=[self.borrow_request.pk]),
            {"due_date": new_due_date, "reason": "Class rescheduled."},
        )

        self.borrow_request.refresh_from_db()
        self.assertEqual(
            self.borrow_request.return_date.isoformat(),
            new_due_date,
        )
        self.assertTrue(
            AuditLog.objects.filter(action="DUE_DATE_REVISED_BEFORE_ISSUE").exists()
        )

    def test_due_date_revision_requires_a_reason(self):
        original_due_date = self.borrow_request.return_date

        self.client.post(
            reverse("revise_approved_due_date", args=[self.borrow_request.pk]),
            {
                "due_date": (timezone.localdate() + timedelta(days=4)).isoformat(),
                "reason": "",
            },
        )

        self.borrow_request.refresh_from_db()
        self.assertEqual(self.borrow_request.return_date, original_due_date)
