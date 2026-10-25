"""A1: account management (list, search, history, activation)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import AuditLog, BorrowRequest, UserProfile
from .helpers import TEST_PASSWORD, make_admin, make_user


class AccountManagementTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_search_filters_accounts(self):
        make_user("alice")
        make_user("bob")

        response = self.client.get(reverse("account_management"), {"q": "alice"})

        self.assertEqual(response.status_code, 200)
        rows = response.context["page_obj"].object_list
        self.assertEqual([row["user"].username for row in rows], ["alice"])

    def test_account_list_is_paginated(self):
        for index in range(12):
            make_user(f"user{index:02d}")

        response = self.client.get(reverse("account_management"))

        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.paginator.per_page, 10)
        self.assertEqual(page_obj.paginator.num_pages, 2)

    def test_account_detail_shows_borrow_request_history(self):
        borrower = make_user("borrower")
        BorrowRequest.objects.create(
            user=borrower,
            purpose="Robotics demonstration",
            return_date=timezone.localdate() + timedelta(days=3),
        )

        response = self.client.get(
            reverse("account_detail", args=[borrower.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Borrowing Request History")
        self.assertContains(response, "Robotics demonstration")

    def test_basic_user_cannot_view_account_history(self):
        borrower = make_user("borrower")
        target = make_user("target")
        self.client.force_login(borrower)

        response = self.client.get(
            reverse("account_detail", args=[target.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_deactivation_blocks_sign_in(self):
        borrower = make_user("borrower")

        self.client.post(reverse("toggle_account_status", args=[borrower.pk]))

        borrower.refresh_from_db()
        self.assertFalse(borrower.is_active)
        self.assertFalse(borrower.profile.is_active)
        self.assertTrue(
            AuditLog.objects.filter(action="ACCOUNT_DEACTIVATED").exists()
        )

        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": "borrower", "password": TEST_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_activation_restores_sign_in(self):
        borrower = make_user("borrower")
        self.client.post(reverse("toggle_account_status", args=[borrower.pk]))

        self.client.post(reverse("toggle_account_status", args=[borrower.pk]))

        borrower.refresh_from_db()
        self.assertTrue(borrower.is_active)
        self.assertTrue(
            AuditLog.objects.filter(action="ACCOUNT_ACTIVATED").exists()
        )

    def test_admin_cannot_deactivate_own_account(self):
        self.client.post(reverse("toggle_account_status", args=[self.admin.pk]))

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertTrue(self.admin.profile.is_active)

    def test_other_admin_can_be_deactivated_while_one_remains(self):
        second_admin = make_admin("second-admin")

        self.client.post(reverse("toggle_account_status", args=[second_admin.pk]))

        second_admin.refresh_from_db()
        self.assertFalse(second_admin.is_active)
        self.assertEqual(
            UserProfile.objects.filter(
                role=UserProfile.ADMIN,
                is_active=True,
            ).count(),
            1,
        )

    def test_basic_user_cannot_toggle_accounts(self):
        borrower = make_user("borrower")
        target = make_user("target")
        self.client.force_login(borrower)

        response = self.client.post(
            reverse("toggle_account_status", args=[target.pk])
        )

        self.assertEqual(response.status_code, 403)
        target.refresh_from_db()
        self.assertTrue(target.is_active)
