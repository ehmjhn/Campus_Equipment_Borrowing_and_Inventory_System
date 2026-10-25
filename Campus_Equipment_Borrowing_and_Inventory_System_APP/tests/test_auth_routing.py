"""U1: public registration and role-aware routing."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..models import UserProfile
from .helpers import TEST_PASSWORD, make_admin, make_user


class RegistrationTests(TestCase):
    def registration_payload(self, **overrides):
        payload = {
            "username": "newuser",
            "first_name": "New",
            "last_name": "Borrower",
            "email": "new@example.com",
            "contact_number": "09171234567",
            "password1": "Str0ng-Pass-123",
            "password2": "Str0ng-Pass-123",
        }
        payload.update(overrides)
        return payload

    def test_registration_page_renders(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Account")

    def test_registration_creates_active_basic_user_and_signs_in(self):
        response = self.client.post(
            reverse("register"),
            self.registration_payload(),
        )

        self.assertRedirects(response, reverse("portal_home"))

        user = User.objects.get(username="newuser")
        self.assertEqual(user.profile.role, UserProfile.BASIC_USER)
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.is_active)
        self.assertEqual(user.profile.contact_number, "09171234567")
        self.assertEqual(user.first_name, "New")
        self.assertTrue(user.check_password("Str0ng-Pass-123"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_registration_ignores_posted_role_and_activation(self):
        self.client.post(
            reverse("register"),
            self.registration_payload(role="ADMIN", is_active="False"),
        )

        user = User.objects.get(username="newuser")
        self.assertEqual(user.profile.role, UserProfile.BASIC_USER)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_registration_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse("register"),
            self.registration_payload(password2="Different-Pass-123"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newuser").exists())
        self.assertIn("password2", response.context["form"].errors)

    def test_registration_rejects_duplicate_username(self):
        make_user("newuser")

        response = self.client.post(
            reverse("register"),
            self.registration_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="newuser").count(), 1)

    def test_superuser_receives_admin_profile_automatically(self):
        superuser = User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password=TEST_PASSWORD,
        )

        self.assertEqual(superuser.profile.role, UserProfile.ADMIN)


class RoleRoutingTests(TestCase):
    def test_basic_user_login_lands_on_portal_landing_page(self):
        user = make_user("borrower")

        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": TEST_PASSWORD},
            follow=True,
        )

        self.assertRedirects(response, reverse("portal_home"))

    def test_admin_login_lands_on_manage_dashboard(self):
        admin = make_admin()

        response = self.client.post(
            reverse("login"),
            {"username": admin.username, "password": TEST_PASSWORD},
            follow=True,
        )

        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_home_redirects_each_role_to_its_area(self):
        basic_user = make_user("borrower")
        self.client.force_login(basic_user)
        self.assertRedirects(self.client.get(reverse("home")), reverse("portal_home"))

        admin = make_admin("second-admin")
        self.client.force_login(admin)
        self.assertRedirects(self.client.get(reverse("home")), reverse("admin_dashboard"))

    def test_anonymous_portal_access_redirects_to_login(self):
        response = self.client.get(reverse("browse_catalog"))
        landing_response = self.client.get(reverse("portal_home"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(landing_response.status_code, 302)
        self.assertIn(reverse("login"), landing_response.url)

    def test_portal_landing_renders_for_basic_user_and_redirects_admin(self):
        basic_user = make_user("borrower")
        self.client.force_login(basic_user)

        response = self.client.get(reverse("portal_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Browse Equipment")

        admin = make_admin("second-admin")
        self.client.force_login(admin)
        self.assertRedirects(
            self.client.get(reverse("portal_home")),
            reverse("admin_dashboard"),
        )
