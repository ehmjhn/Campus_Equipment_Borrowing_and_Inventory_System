"""U2: catalog browsing; U3: submitting requests; U4: tracking and cancelling."""

from datetime import timedelta

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
    ReturnRecord,
    SystemSetting,
    UnitAllocation,
)
from .helpers import make_item, make_unit, make_user, reserve


class PortalTestCase(TestCase):
    def setUp(self):
        self.user = make_user("borrower")
        self.client.force_login(self.user)

        self.category = Category.objects.create(name="Audio")
        self.item = CatalogItem.objects.create(
            category=self.category,
            name="Microphone",
        )
        self.second_item = CatalogItem.objects.create(
            category=self.category,
            name="Speaker",
        )
        self.unit = make_unit(self.item, asset_code="MIC-001")


class CatalogTests(PortalTestCase):
    def test_catalog_and_request_form_render_for_basic_user(self):
        catalog_response = self.client.get(reverse("browse_catalog"))
        form_response = self.client.get(reverse("borrow_request_create"))

        self.assertEqual(catalog_response.status_code, 200)
        self.assertContains(catalog_response, "Microphone")
        self.assertContains(catalog_response, "Available now:</strong> 1")
        self.assertEqual(form_response.status_code, 200)

    def test_catalog_shows_total_serviceable_and_available_quantities(self):
        make_unit(self.item, asset_code="MIC-002", status=EquipmentUnit.RESERVED)
        make_unit(self.item, asset_code="MIC-003", status=EquipmentUnit.ISSUED)
        make_unit(self.item, asset_code="MIC-004", status=EquipmentUnit.MAINTENANCE)
        make_unit(self.item, asset_code="MIC-005", status=EquipmentUnit.RETIRED)

        response = self.client.get(reverse("browse_catalog"))

        self.assertContains(response, "Total serviceable:</strong> 3")
        self.assertContains(response, "Available now:</strong> 1")

    def test_catalog_search_filters_by_item_name(self):
        response = self.client.get(reverse("browse_catalog"), {"q": "speaker"})

        self.assertContains(response, "Speaker")
        self.assertNotContains(response, "Microphone")

    def test_catalog_search_filters_by_category(self):
        response = self.client.get(reverse("browse_catalog"), {"q": "audio"})

        self.assertContains(response, "Microphone")
        self.assertContains(response, "Speaker")

    def test_catalog_hides_archived_items_and_categories(self):
        archived_item = make_item("Archived Item")
        archived_item.is_archived = True
        archived_item.save(update_fields=["is_archived"])

        archived_category = Category.objects.create(
            name="Archived Category",
            is_archived=True,
        )
        item_in_archived_category = CatalogItem.objects.create(
            category=archived_category,
            name="Hidden Item",
        )
        make_unit(item_in_archived_category, asset_code="HID-001")

        response = self.client.get(reverse("browse_catalog"))

        self.assertNotContains(response, "Archived Item")
        self.assertNotContains(response, "Hidden Item")

    def test_catalog_availability_counts_only_available_units(self):
        make_unit(self.item, asset_code="MIC-002", status=EquipmentUnit.RESERVED)
        make_unit(self.item, asset_code="MIC-003", status=EquipmentUnit.MAINTENANCE)

        response = self.client.get(reverse("browse_catalog"))

        self.assertContains(response, "Available now:</strong> 1")

    def test_request_form_prefills_item_from_query_string(self):
        response = self.client.get(
            reverse("borrow_request_create"),
            {"item": self.item.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["item_1"].value(),
            str(self.item.pk),
        )
        self.assertEqual(response.context["form"]["quantity_1"].value(), 1)


class RequestSubmissionTests(PortalTestCase):
    def test_submit_creates_pending_request_without_reserving_units(self):
        response = self.client.post(
            reverse("borrow_request_create"),
            {
                "purpose": "For a class presentation",
                "return_date": (
                    timezone.localdate() + timedelta(days=2)
                ).isoformat(),
                "item_1": str(self.item.pk),
                "quantity_1": "1",
                "item_2": str(self.second_item.pk),
                "quantity_2": "2",
            },
        )

        self.assertRedirects(response, reverse("request_history"))
        borrow_request = BorrowRequest.objects.get(user=self.user)
        self.assertEqual(borrow_request.status, BorrowRequest.PENDING)
        self.assertEqual(borrow_request.items.count(), 2)
        self.assertFalse(UnitAllocation.objects.exists())
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, EquipmentUnit.AVAILABLE)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.user,
                action="REQUEST_SUBMITTED",
            ).exists()
        )

    def test_submit_rejects_duplicate_items_quantity_and_dates_over_limits(self):
        SystemSetting.objects.create(key="max_quantity", value="1")
        response = self.client.post(
            reverse("borrow_request_create"),
            {
                "purpose": "For a class presentation",
                "return_date": (
                    timezone.localdate() + timedelta(days=8)
                ).isoformat(),
                "item_1": str(self.item.pk),
                "quantity_1": "2",
                "item_2": str(self.item.pk),
                "quantity_2": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BorrowRequest.objects.count(), 0)
        form = response.context["form"]
        self.assertTrue(form.errors)
        self.assertIn("return_date", form.errors)
        self.assertIn("quantity_1", form.errors)
        self.assertIn("item_2", form.errors)

    def test_submit_rejects_past_return_date(self):
        response = self.client.post(
            reverse("borrow_request_create"),
            {
                "purpose": "For a class presentation",
                "return_date": timezone.localdate().isoformat(),
                "item_1": str(self.item.pk),
                "quantity_1": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("return_date", response.context["form"].errors)
        self.assertFalse(BorrowRequest.objects.exists())


class RequestHistoryTests(PortalTestCase):
    def test_history_is_limited_to_owner_and_cannot_cancel_another_users_request(self):
        other_user = make_user("other-borrower")
        other_request = BorrowRequest.objects.create(
            user=other_user,
            purpose="Private request",
            return_date=timezone.localdate() + timedelta(days=2),
        )

        response = self.client.get(reverse("request_history"))
        cancel_response = self.client.post(
            reverse("cancel_borrow_request", args=[other_request.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private request")
        self.assertEqual(cancel_response.status_code, 404)
        other_request.refresh_from_db()
        self.assertEqual(other_request.status, BorrowRequest.PENDING)

    def test_cancelling_pending_request_marks_it_cancelled(self):
        borrow_request = BorrowRequest.objects.create(
            user=self.user,
            purpose="No longer needed",
            return_date=timezone.localdate() + timedelta(days=2),
        )

        response = self.client.post(
            reverse("cancel_borrow_request", args=[borrow_request.pk]),
        )

        self.assertRedirects(response, reverse("request_history"))
        borrow_request.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.CANCELLED)
        self.assertTrue(
            AuditLog.objects.filter(action="REQUEST_CANCELLED").exists()
        )

    def test_cancelling_approved_request_releases_reserved_allocations(self):
        borrow_request = BorrowRequest.objects.create(
            user=self.user,
            purpose="For a class presentation",
            return_date=timezone.localdate() + timedelta(days=2),
            status=BorrowRequest.APPROVED,
        )
        request_item = RequestItem.objects.create(
            request=borrow_request,
            catalog_item=self.item,
            quantity=1,
        )
        reserve(request_item, self.unit)

        response = self.client.post(
            reverse("cancel_borrow_request", args=[borrow_request.pk]),
        )

        self.assertRedirects(response, reverse("request_history"))
        borrow_request.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.CANCELLED)
        self.assertEqual(self.unit.status, EquipmentUnit.AVAILABLE)
        allocation = UnitAllocation.objects.get()
        self.assertIsNotNone(allocation.released_at)
        self.assertEqual(
            allocation.release_reason,
            UnitAllocation.CANCELLED,
        )
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.user,
                action="REQUEST_CANCELLED",
            ).exists()
        )

    def test_issued_request_cannot_be_cancelled(self):
        borrow_request = BorrowRequest.objects.create(
            user=self.user,
            purpose="Already issued",
            return_date=timezone.localdate() + timedelta(days=2),
            status=BorrowRequest.ISSUED,
        )

        response = self.client.post(
            reverse("cancel_borrow_request", args=[borrow_request.pk]),
        )

        self.assertRedirects(response, reverse("request_history"))
        borrow_request.refresh_from_db()
        self.assertEqual(borrow_request.status, BorrowRequest.ISSUED)

    def test_history_shows_issued_and_returned_unit_details(self):
        borrow_request = BorrowRequest.objects.create(
            user=self.user,
            purpose="For a class presentation",
            return_date=timezone.localdate() + timedelta(days=2),
            status=BorrowRequest.RETURNED,
        )
        request_item = RequestItem.objects.create(
            request=borrow_request,
            catalog_item=self.item,
            quantity=1,
        )
        UnitAllocation.objects.create(
            request_item=request_item,
            unit=self.unit,
        )
        loan = Loan.objects.create(
            request=borrow_request,
            issued_by=self.user,
        )
        ReturnRecord.objects.create(
            loan=loan,
            unit=self.unit,
            condition_on_return="Good",
            received_by=self.user,
        )

        response = self.client.get(reverse("request_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Due date:")
        self.assertContains(response, "Released:")
        self.assertContains(response, "Asset MIC-001")
        self.assertContains(response, "returned")
        self.assertContains(response, "Good")


class ProfileAndAccessTests(PortalTestCase):
    def test_profile_update_saves_name_and_contact_number(self):
        response = self.client.post(
            reverse("profile_view"),
            {
                "first_name": "Maria",
                "last_name": "Santos",
                "contact_number": "09171234567",
            },
        )

        self.assertRedirects(response, reverse("profile_view"))
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, "Maria")
        self.assertEqual(self.user.last_name, "Santos")
        self.assertEqual(self.user.profile.contact_number, "09171234567")

    def test_portal_requires_active_basic_user_profile(self):
        self.user.profile.is_active = False
        self.user.profile.save(update_fields=["is_active"])

        response = self.client.get(reverse("browse_catalog"))

        self.assertEqual(response.status_code, 403)

    def test_basic_user_cannot_open_admin_pages(self):
        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_use_basic_user_portal(self):
        admin = make_user("admin-user")
        admin.profile.role = "ADMIN"
        admin.profile.save(update_fields=["role"])
        self.client.force_login(admin)

        response = self.client.get(reverse("browse_catalog"))

        self.assertEqual(response.status_code, 403)
