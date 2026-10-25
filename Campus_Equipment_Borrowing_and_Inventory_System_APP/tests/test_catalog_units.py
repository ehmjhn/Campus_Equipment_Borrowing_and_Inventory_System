"""A2: equipment catalog CRUD, archiving, and physical unit lifecycle."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import AuditLog, CatalogItem, Category, EquipmentUnit
from .helpers import (
    add_item,
    make_admin,
    make_item,
    make_request,
    make_unit,
    make_user,
)


class CategoryManagementTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_category_is_created_and_audited(self):
        response = self.client.post(
            reverse("category_create"),
            {"name": "Robotics", "description": "Robot kits"},
        )

        self.assertRedirects(response, reverse("category_management"))
        category = Category.objects.get(name="Robotics")
        self.assertTrue(
            AuditLog.objects.filter(
                action="CATEGORY_CREATED",
                details__contains=category.name,
            ).exists()
        )

    def test_duplicate_category_name_is_rejected(self):
        Category.objects.create(name="Robotics")

        self.client.post(reverse("category_create"), {"name": "robotics"})

        self.assertEqual(Category.objects.filter(name__iexact="Robotics").count(), 1)

    def test_category_can_be_edited(self):
        category = Category.objects.create(name="Robotics")

        self.client.post(
            reverse("category_edit", args=[category.pk]),
            {"name": "Robotics and Drones", "description": "Updated"},
        )

        category.refresh_from_db()
        self.assertEqual(category.name, "Robotics and Drones")
        self.assertTrue(AuditLog.objects.filter(action="CATEGORY_UPDATED").exists())

    def test_category_archive_blocked_while_it_has_active_items(self):
        category = Category.objects.create(name="Robotics")
        CatalogItem.objects.create(category=category, name="Robot Arm")

        self.client.post(reverse("category_archive", args=[category.pk]))

        category.refresh_from_db()
        self.assertFalse(category.is_archived)

    def test_category_archive_succeeds_when_items_are_archived(self):
        category = Category.objects.create(name="Robotics")
        item = CatalogItem.objects.create(
            category=category,
            name="Robot Arm",
            is_archived=True,
        )

        self.client.post(reverse("category_archive", args=[category.pk]))

        category.refresh_from_db()
        self.assertTrue(category.is_archived)
        item.refresh_from_db()
        self.assertTrue(item.is_archived)


class CatalogItemManagementTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)
        self.category = Category.objects.create(name="Computing")

    def test_item_is_created_and_audited(self):
        self.client.post(
            reverse("catalog_item_create"),
            {"name": "Tablet", "description": "10-inch", "category": self.category.pk},
        )

        item = CatalogItem.objects.get(name="Tablet")
        self.assertTrue(
            AuditLog.objects.filter(
                action="CATALOG_ITEM_CREATED",
                details__contains=item.name,
            ).exists()
        )

    def test_item_can_be_edited(self):
        item = CatalogItem.objects.create(category=self.category, name="Tablet")

        self.client.post(
            reverse("catalog_item_edit", args=[item.pk]),
            {"name": "Tablet Pro", "description": "11-inch", "category": self.category.pk},
        )

        item.refresh_from_db()
        self.assertEqual(item.name, "Tablet Pro")
        self.assertTrue(AuditLog.objects.filter(action="CATALOG_ITEM_UPDATED").exists())

    def test_archive_blocked_by_reserved_units(self):
        item = CatalogItem.objects.create(category=self.category, name="Tablet")
        make_unit(item, status=EquipmentUnit.RESERVED)

        self.client.post(reverse("catalog_item_archive", args=[item.pk]))

        item.refresh_from_db()
        self.assertFalse(item.is_archived)

    def test_archive_blocked_by_open_requests(self):
        item = CatalogItem.objects.create(category=self.category, name="Tablet")
        borrower = make_user("borrower")
        pending = make_request(borrower)
        add_item(pending, item)

        self.client.post(reverse("catalog_item_archive", args=[item.pk]))

        item.refresh_from_db()
        self.assertFalse(item.is_archived)

    def test_archive_succeeds_without_open_transactions(self):
        item = CatalogItem.objects.create(category=self.category, name="Tablet")
        make_unit(item)

        self.client.post(reverse("catalog_item_archive", args=[item.pk]))

        item.refresh_from_db()
        self.assertTrue(item.is_archived)
        self.assertEqual(item.units.count(), 1)  # history preserved

    def test_basic_user_cannot_archive_items(self):
        borrower = make_user("borrower")
        item = CatalogItem.objects.create(category=self.category, name="Tablet")
        self.client.force_login(borrower)

        response = self.client.post(reverse("catalog_item_archive", args=[item.pk]))

        self.assertEqual(response.status_code, 403)


class PhysicalUnitTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)
        self.item = make_item()

    def test_unit_registration_requires_unique_asset_code(self):
        make_unit(self.item, asset_code="AST-001")

        self.client.post(
            reverse("equipment_unit_create"),
            {
                "catalog_item": self.item.pk,
                "asset_code": "AST-001",
                "condition": "Good",
                "acquisition_date": timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(EquipmentUnit.objects.count(), 1)

    def test_unit_details_can_be_updated_with_audit(self):
        unit = make_unit(self.item, asset_code="AST-002")

        self.client.post(
            reverse("equipment_unit_update", args=[unit.pk]),
            {
                "condition": "Fair - scratched lid",
                "acquisition_date": "2025-01-15",
            },
        )

        unit.refresh_from_db()
        self.assertEqual(unit.condition, "Fair - scratched lid")
        self.assertEqual(unit.acquisition_date.isoformat(), "2025-01-15")
        self.assertTrue(
            AuditLog.objects.filter(action="EQUIPMENT_UNIT_UPDATED").exists()
        )

    def test_unit_edit_blocked_while_issued(self):
        unit = make_unit(self.item, status=EquipmentUnit.ISSUED)

        self.client.post(
            reverse("equipment_unit_update", args=[unit.pk]),
            {"condition": "Changed", "acquisition_date": "2025-01-15"},
        )

        unit.refresh_from_db()
        self.assertEqual(unit.condition, "Good")

    def test_unit_can_be_retired_and_restored(self):
        unit = make_unit(self.item)

        self.client.post(reverse("equipment_unit_retire", args=[unit.pk]))
        unit.refresh_from_db()
        self.assertEqual(unit.status, EquipmentUnit.RETIRED)

        self.client.post(reverse("equipment_unit_restore", args=[unit.pk]))
        unit.refresh_from_db()
        self.assertEqual(unit.status, EquipmentUnit.AVAILABLE)

        self.assertTrue(
            AuditLog.objects.filter(action="EQUIPMENT_UNIT_RETIRED").exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="EQUIPMENT_UNIT_RESTORED").exists()
        )

    def test_retire_blocked_while_unit_is_on_loan(self):
        unit = make_unit(self.item, status=EquipmentUnit.ISSUED)

        self.client.post(reverse("equipment_unit_retire", args=[unit.pk]))

        unit.refresh_from_db()
        self.assertEqual(unit.status, EquipmentUnit.ISSUED)

    def test_physical_units_can_be_filtered_by_category_item_and_status(self):
        other_category = Category.objects.create(name="Audio")
        other_item = CatalogItem.objects.create(
            category=other_category,
            name="Speaker",
        )
        laptop = make_unit(self.item, asset_code="AST-100")
        speaker = make_unit(
            other_item,
            asset_code="AST-200",
            status=EquipmentUnit.MAINTENANCE,
        )

        category_response = self.client.get(
            reverse("physical_units_management"),
            {"category": other_category.pk},
        )
        self.assertEqual(
            [unit.pk for unit in category_response.context["equipment_units"]],
            [speaker.pk],
        )

        item_response = self.client.get(
            reverse("physical_units_management"),
            {"item": self.item.pk},
        )
        self.assertEqual(
            [unit.pk for unit in item_response.context["equipment_units"]],
            [laptop.pk],
        )

        status_response = self.client.get(
            reverse("physical_units_management"),
            {"status": EquipmentUnit.MAINTENANCE},
        )
        self.assertEqual(
            [unit.pk for unit in status_response.context["equipment_units"]],
            [speaker.pk],
        )

    def test_physical_units_page_shows_reconciliation_summary(self):
        make_unit(self.item, asset_code="AST-010")

        response = self.client.get(reverse("physical_units_management"))

        self.assertEqual(response.status_code, 200)
        rows = response.context["reconciliation_rows"]
        self.assertEqual(rows[0]["total"], 1)
        self.assertEqual(rows[0]["item"], self.item)
        self.assertEqual(len(rows), 1)
