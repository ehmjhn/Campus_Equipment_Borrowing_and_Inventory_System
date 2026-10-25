"""Section 7: data-integrity constraints, protection, and reconciliation.

These tests guard the invariants that make inventory counts trustworthy:

* one physical unit can belong to at most one allocation,
* a request cannot list the same catalog item twice,
* quantities are always positive,
* catalog items referenced by request history cannot be deleted, and
* reserved units without an allocation can be reconciled safely.
"""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from ..models import (
    AuditLog,
    BorrowRequest,
    CatalogItem,
    EquipmentUnit,
    RequestItem,
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


class ConstraintTests(TestCase):
    def setUp(self):
        self.borrower = make_user("borrower")
        self.item = make_item()
        self.unit = make_unit(self.item, asset_code="UNQ-001")

    def test_unit_can_only_be_allocated_once(self):
        first = add_item(make_request(self.borrower, purpose="First"), self.item)
        second = add_item(make_request(self.borrower, purpose="Second"), self.item)
        UnitAllocation.objects.create(request_item=first, unit=self.unit)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UnitAllocation.objects.create(request_item=second, unit=self.unit)

    def test_released_unit_can_be_allocated_again(self):
        first = add_item(make_request(self.borrower, purpose="First"), self.item)
        second = add_item(make_request(self.borrower, purpose="Second"), self.item)

        allocation = UnitAllocation.objects.create(
            request_item=first,
            unit=self.unit,
        )
        allocation.release(UnitAllocation.RETURNED)

        replacement = UnitAllocation.objects.create(
            request_item=second,
            unit=self.unit,
        )

        self.assertIsNone(replacement.released_at)
        self.assertIsNotNone(replacement.allocated_at)
        self.assertEqual(
            UnitAllocation.objects.filter(unit=self.unit).count(),
            2,
        )

    def test_request_cannot_list_the_same_catalog_item_twice(self):
        borrow_request = make_request(self.borrower)
        add_item(borrow_request, self.item)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RequestItem.objects.create(
                    request=borrow_request,
                    catalog_item=self.item,
                    quantity=1,
                )

    def test_request_item_quantity_must_be_at_least_one(self):
        borrow_request = make_request(self.borrower)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RequestItem.objects.create(
                    request=borrow_request,
                    catalog_item=self.item,
                    quantity=0,
                )

    def test_catalog_item_with_request_history_cannot_be_deleted(self):
        borrow_request = make_request(self.borrower)
        add_item(borrow_request, self.item)

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                self.item.delete()

        self.assertTrue(CatalogItem.objects.filter(pk=self.item.pk).exists())

    def test_allocated_unit_cannot_be_deleted(self):
        request_item = add_item(make_request(self.borrower), self.item)
        UnitAllocation.objects.create(request_item=request_item, unit=self.unit)

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                self.unit.delete()

        self.assertTrue(EquipmentUnit.objects.filter(pk=self.unit.pk).exists())


class ReconciliationTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.borrower = make_user("borrower")
        self.item = make_item()
        self.client.force_login(self.admin)

    def test_reconcile_releases_orphaned_reserved_units(self):
        orphan = make_unit(
            self.item,
            asset_code="ORP-001",
            status=EquipmentUnit.RESERVED,
        )

        response = self.client.post(reverse("reconcile_inventory"))

        self.assertRedirects(response, reverse("physical_units_management"))
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, EquipmentUnit.AVAILABLE)
        self.assertTrue(
            AuditLog.objects.filter(
                action="INVENTORY_RECONCILED",
                details__contains="ORP-001",
            ).exists()
        )

    def test_reconcile_keeps_correctly_allocated_reserved_units(self):
        borrow_request = make_request(self.borrower, status=BorrowRequest.APPROVED)
        request_item = add_item(borrow_request, self.item)
        unit = make_unit(self.item, asset_code="RSV-001")
        reserve(request_item, unit)

        self.client.post(reverse("reconcile_inventory"))

        unit.refresh_from_db()
        self.assertEqual(unit.status, EquipmentUnit.RESERVED)
        self.assertTrue(UnitAllocation.objects.filter(unit=unit).exists())

    def test_reconciliation_panel_lists_orphaned_units(self):
        orphan = make_unit(
            self.item,
            asset_code="ORP-002",
            status=EquipmentUnit.RESERVED,
        )

        response = self.client.get(reverse("physical_units_management"))

        self.assertEqual(response.status_code, 200)
        listed = response.context["anomalies"]["orphaned_reserved"]
        self.assertEqual([unit.pk for unit in listed], [orphan.pk])

    def test_reconciliation_panel_reports_no_discrepancies(self):
        make_unit(self.item, asset_code="OK-001")

        response = self.client.get(reverse("physical_units_management"))

        anomalies = response.context["anomalies"]
        self.assertFalse(anomalies["orphaned_reserved"])
        self.assertFalse(anomalies["stale_allocations"])
        self.assertFalse(anomalies["issued_without_active_loan"])

    def test_returned_allocations_are_not_reported_as_stale(self):
        borrow_request = make_request(
            self.borrower,
            status=BorrowRequest.RETURNED,
        )
        request_item = add_item(borrow_request, self.item)
        returned_unit = make_unit(self.item, asset_code="RET-100")
        UnitAllocation.objects.create(
            request_item=request_item,
            unit=returned_unit,
        )

        response = self.client.get(reverse("physical_units_management"))

        self.assertFalse(response.context["anomalies"]["stale_allocations"])

    def test_approved_allocation_without_reserved_unit_is_stale(self):
        borrow_request = make_request(
            self.borrower,
            status=BorrowRequest.APPROVED,
        )
        request_item = add_item(borrow_request, self.item)
        available_unit = make_unit(self.item, asset_code="STL-001")
        UnitAllocation.objects.create(
            request_item=request_item,
            unit=available_unit,
        )

        response = self.client.get(reverse("physical_units_management"))

        stale = response.context["anomalies"]["stale_allocations"]
        self.assertEqual([row.pk for row in stale], [
            UnitAllocation.objects.get().pk,
        ])

    def test_reconcile_requires_admin_role(self):
        self.client.force_login(self.borrower)

        response = self.client.post(reverse("reconcile_inventory"))

        self.assertEqual(response.status_code, 403)
