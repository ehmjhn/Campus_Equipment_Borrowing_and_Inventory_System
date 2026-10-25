"""A5: returns and overdue handling; A6: maintenance records."""

from django.test import TestCase
from django.urls import reverse

from ..models import (
    AuditLog,
    BorrowRequest,
    EquipmentUnit,
    Loan,
    MaintenanceRecord,
    ReturnRecord,
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


def build_issued_loan(borrower, item, asset_codes):
    """Create an issued request whose units are allocated to one loan."""
    borrow_request = make_request(borrower, status=BorrowRequest.ISSUED)
    request_item = add_item(borrow_request, item, quantity=len(asset_codes))
    units = [make_unit(item, asset_code=code) for code in asset_codes]

    for unit in units:
        reserve(request_item, unit)
        unit.status = EquipmentUnit.ISSUED
        unit.save(update_fields=["status"])

    loan = Loan.objects.create(request=borrow_request, issued_by=borrower)
    return borrow_request, request_item, units, loan


class ReturnRecordingTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.borrower = make_user("borrower")
        self.item = make_item()
        self.client.force_login(self.admin)

    def record_return(self, loan, unit, **payload):
        body = {"condition_status": "Good"}
        body.update(payload)
        return self.client.post(
            reverse("record_unit_return", args=[loan.pk, unit.pk]),
            body,
        )

    def test_partial_return_marks_request_partially_returned(self):
        borrow_request, _, units, loan = build_issued_loan(
            self.borrower,
            self.item,
            ["RET-001", "RET-002"],
        )

        response = self.record_return(loan, units[0])

        self.assertRedirects(response, reverse("return_management"))
        borrow_request.refresh_from_db()
        units[0].refresh_from_db()
        units[1].refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.PARTIALLY_RETURNED)
        self.assertEqual(units[0].status, EquipmentUnit.AVAILABLE)
        self.assertEqual(units[1].status, EquipmentUnit.ISSUED)
        self.assertEqual(ReturnRecord.objects.count(), 1)
        self.assertTrue(
            AuditLog.objects.filter(action="EQUIPMENT_UNIT_RETURNED").exists()
        )

    def test_return_releases_the_unit_allocation(self):
        _, _, units, loan = build_issued_loan(
            self.borrower,
            self.item,
            ["RET-001"],
        )

        self.record_return(loan, units[0])

        allocation = UnitAllocation.objects.get(unit=units[0])
        self.assertIsNotNone(allocation.released_at)
        self.assertEqual(
            allocation.release_reason,
            UnitAllocation.RETURNED,
        )

    def test_final_return_marks_request_returned(self):
        borrow_request, _, units, loan = build_issued_loan(
            self.borrower,
            self.item,
            ["RET-001", "RET-002"],
        )

        self.record_return(loan, units[0])
        self.record_return(loan, units[1])

        borrow_request.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.RETURNED)
        self.assertEqual(ReturnRecord.objects.count(), 2)

    def test_return_cannot_be_recorded_twice(self):
        _, _, units, loan = build_issued_loan(
            self.borrower,
            self.item,
            ["RET-001"],
        )

        self.record_return(loan, units[0])
        self.record_return(loan, units[0])

        self.assertEqual(ReturnRecord.objects.count(), 1)

    def test_invalid_condition_is_rejected(self):
        _, _, units, loan = build_issued_loan(
            self.borrower,
            self.item,
            ["RET-001"],
        )

        response = self.record_return(loan, units[0], condition_status="Lost")

        self.assertRedirects(response, reverse("return_management"))
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, EquipmentUnit.ISSUED)
        self.assertFalse(ReturnRecord.objects.exists())

    def test_damaged_return_sends_unit_to_maintenance(self):
        _, _, units, loan = build_issued_loan(
            self.borrower,
            self.item,
            ["RET-001"],
        )

        self.record_return(
            loan,
            units[0],
            condition_status="Damaged",
            condition_notes="Screen cracked",
        )

        units[0].refresh_from_db()
        self.assertEqual(units[0].status, EquipmentUnit.MAINTENANCE)
        self.assertEqual(
            units[0].condition,
            "Damaged: Screen cracked",
        )
        maintenance = MaintenanceRecord.objects.get(unit=units[0])
        self.assertIsNone(maintenance.fixed_at)
        self.assertTrue(
            AuditLog.objects.filter(
                action="DAMAGED_UNIT_SENT_TO_MAINTENANCE"
            ).exists()
        )

    def test_return_rejected_for_inactive_loan(self):
        borrow_request, _, units, loan = build_issued_loan(
            self.borrower,
            self.item,
            ["RET-001"],
        )
        borrow_request.status = BorrowRequest.RETURNED
        borrow_request.save(update_fields=["status"])

        self.record_return(loan, units[0])

        self.assertFalse(ReturnRecord.objects.exists())
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, EquipmentUnit.ISSUED)

    def test_unit_not_allocated_to_loan_is_rejected(self):
        _, _, units, loan = build_issued_loan(
            self.borrower,
            self.item,
            ["RET-001"],
        )
        other_unit = make_unit(self.item, asset_code="RET-999")

        self.record_return(loan, other_unit)

        self.assertFalse(ReturnRecord.objects.exists())
        other_unit.refresh_from_db()
        self.assertEqual(other_unit.status, EquipmentUnit.AVAILABLE)
        self.assertEqual(units[0].status, EquipmentUnit.ISSUED)


class MaintenanceTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.item = make_item()
        self.unit = make_unit(self.item, asset_code="MNT-001")
        self.client.force_login(self.admin)

    def open_record(self, **payload):
        body = {"unit_id": self.unit.pk, "problem_description": "Battery failing"}
        body.update(payload)
        return self.client.post(reverse("open_maintenance_record"), body)

    def test_open_maintenance_marks_unit_and_audits(self):
        response = self.open_record()

        self.assertRedirects(response, reverse("maintenance_management"))
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, EquipmentUnit.MAINTENANCE)
        record = MaintenanceRecord.objects.get(unit=self.unit)
        self.assertIsNone(record.fixed_at)
        self.assertTrue(AuditLog.objects.filter(action="MAINTENANCE_OPENED").exists())

    def test_open_maintenance_requires_a_problem_description(self):
        self.open_record(problem_description="")

        self.assertFalse(MaintenanceRecord.objects.exists())
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, EquipmentUnit.AVAILABLE)

    def test_open_maintenance_rejected_for_issued_unit(self):
        self.unit.status = EquipmentUnit.ISSUED
        self.unit.save(update_fields=["status"])

        self.open_record()

        self.assertFalse(MaintenanceRecord.objects.exists())

    def test_open_maintenance_rejected_when_record_already_open(self):
        self.open_record()
        self.open_record(problem_description="Second problem")

        self.assertEqual(MaintenanceRecord.objects.count(), 1)

    def test_close_requires_action_taken(self):
        self.open_record()
        record = MaintenanceRecord.objects.get(unit=self.unit)

        response = self.client.post(
            reverse("close_maintenance_record", args=[record.pk]),
            {"action_taken": ""},
        )

        self.assertRedirects(response, reverse("maintenance_management"))
        record.refresh_from_db()
        self.assertIsNone(record.fixed_at)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, EquipmentUnit.MAINTENANCE)

    def test_close_returns_unit_to_available_and_audits(self):
        self.open_record()
        record = MaintenanceRecord.objects.get(unit=self.unit)

        self.client.post(
            reverse("close_maintenance_record", args=[record.pk]),
            {"action_taken": "Replaced the battery"},
        )

        record.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertIsNotNone(record.fixed_at)
        self.assertEqual(record.action_taken, "Replaced the battery")
        self.assertEqual(record.handled_by, self.admin)
        self.assertEqual(self.unit.status, EquipmentUnit.AVAILABLE)
        self.assertTrue(AuditLog.objects.filter(action="MAINTENANCE_CLOSED").exists())

    def test_closed_record_cannot_be_closed_again(self):
        self.open_record()
        record = MaintenanceRecord.objects.get(unit=self.unit)
        self.client.post(
            reverse("close_maintenance_record", args=[record.pk]),
            {"action_taken": "Replaced the battery"},
        )
        first_fixed_at = MaintenanceRecord.objects.get(pk=record.pk).fixed_at

        self.client.post(
            reverse("close_maintenance_record", args=[record.pk]),
            {"action_taken": "Tried again"},
        )

        record.refresh_from_db()
        self.assertEqual(record.fixed_at, first_fixed_at)
        self.assertEqual(record.action_taken, "Replaced the battery")

    def test_close_rejected_while_unit_is_issued(self):
        record = MaintenanceRecord.objects.create(
            unit=self.unit,
            problem_description="Reported earlier",
            handled_by=self.admin,
        )
        self.unit.status = EquipmentUnit.ISSUED
        self.unit.save(update_fields=["status"])

        self.client.post(
            reverse("close_maintenance_record", args=[record.pk]),
            {"action_taken": "Replaced the battery"},
        )

        record.refresh_from_db()
        self.assertIsNone(record.fixed_at)

    def test_closing_retired_unit_does_not_return_it_to_service(self):
        record = MaintenanceRecord.objects.create(
            unit=self.unit,
            problem_description="Assessed for repair",
            handled_by=self.admin,
        )
        self.unit.status = EquipmentUnit.RETIRED
        self.unit.save(update_fields=["status"])

        self.client.post(
            reverse("close_maintenance_record", args=[record.pk]),
            {"action_taken": "Declared beyond economical repair"},
        )

        record.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertIsNotNone(record.fixed_at)
        self.assertEqual(self.unit.status, EquipmentUnit.RETIRED)
