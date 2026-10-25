"""Shared builders for the test suite.

Keeping the setup here means each test module states only what matters for the
scenario it covers (which is also what makes the suite easy to trace back to a
module or team member during the defense).
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from ..models import (
    BorrowRequest,
    CatalogItem,
    Category,
    EquipmentUnit,
    RequestItem,
    UnitAllocation,
    UserProfile,
)

TEST_PASSWORD = "test-pass-123"


def make_user(username, role=UserProfile.BASIC_USER, **extra):
    user = User.objects.create_user(
        username=username,
        password=TEST_PASSWORD,
        **extra,
    )
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role"])
    return user


def make_admin(username="admin"):
    return make_user(username, role=UserProfile.ADMIN)


def make_item(name="Laptop", category_name="Computing"):
    category, _ = Category.objects.get_or_create(name=category_name)
    return CatalogItem.objects.create(category=category, name=name)


def make_unit(item, asset_code="AST-001", status=EquipmentUnit.AVAILABLE, **extra):
    return EquipmentUnit.objects.create(
        catalog_item=item,
        asset_code=asset_code,
        condition=extra.pop("condition", "Good"),
        acquisition_date=extra.pop("acquisition_date", timezone.localdate()),
        status=status,
        **extra,
    )


def make_request(user, status=BorrowRequest.PENDING, days=3, purpose="Class use"):
    return BorrowRequest.objects.create(
        user=user,
        purpose=purpose,
        return_date=timezone.localdate() + timedelta(days=days),
        status=status,
    )


def add_item(borrow_request, item, quantity=1):
    return RequestItem.objects.create(
        request=borrow_request,
        catalog_item=item,
        quantity=quantity,
    )


def reserve(request_item, unit):
    """Mark a unit reserved and attach it to a request item."""
    unit.status = EquipmentUnit.RESERVED
    unit.save(update_fields=["status"])
    return UnitAllocation.objects.create(request_item=request_item, unit=unit)
