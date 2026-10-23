from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class UserProfile(models.Model):
    ADMIN = 'ADMIN'
    BASIC_USER = 'BASIC_USER'
    ROLE_CHOICES = [
        (ADMIN, 'Admin'),
        (BASIC_USER, 'Basic User'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=BASIC_USER)
    contact_number = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class CatalogItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class EquipmentUnit(models.Model):
    AVAILABLE = 'Available'
    RESERVED = 'Reserved'
    ISSUED = 'Issued'
    MAINTENANCE = 'Maintenance'
    RETIRED = 'Retired'
    STATUS_CHOICES = [
        (AVAILABLE, 'Available'),
        (RESERVED, 'Reserved'),
        (ISSUED, 'Issued'),
        (MAINTENANCE, 'Maintenance'),
        (RETIRED, 'Retired'),
    ]

    catalog_item = models.ForeignKey(CatalogItem, on_delete=models.CASCADE, related_name='units')
    asset_code = models.CharField(max_length=50, unique=True)
    condition = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=AVAILABLE)
    acquisition_date = models.DateField()

    def __str__(self):
        return f"{self.asset_code} - {self.catalog_item.name}"

class BorrowRequest(models.Model):
    PENDING = 'Pending'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'
    CANCELLED = 'Cancelled'
    ISSUED = 'Issued'
    PARTIALLY_RETURNED = 'Partially Returned'
    RETURNED = 'Returned'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
        (CANCELLED, 'Cancelled'),
        (ISSUED, 'Issued'),
        (PARTIALLY_RETURNED, 'Partially Returned'),
        (RETURNED, 'Returned'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='borrow_requests')
    purpose = models.TextField()
    requested_at = models.DateTimeField(auto_now_add=True)
    return_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    admin_remarks = models.TextField(blank=True)

    def __str__(self):
        return f"Request #{self.id} by {self.user.username}"

class RequestItem(models.Model):
    request = models.ForeignKey(
        BorrowRequest,
        on_delete=models.CASCADE,
        related_name='items'
    )
    catalog_item = models.ForeignKey(
        CatalogItem,
        on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['request', 'catalog_item'],
                name='unique_catalog_item_per_request'
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name='request_item_quantity_gte_1'
            ),
        ]

    def __str__(self):
        return (
            f"{self.quantity}x {self.catalog_item.name} "
            f"for Request #{self.request_id}"
        )

class UnitAllocation(models.Model):
    request_item = models.ForeignKey(
        RequestItem,
        on_delete=models.CASCADE,
        related_name='allocations'
    )
    unit = models.ForeignKey(
        EquipmentUnit,
        on_delete=models.PROTECT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['unit'],
                name='unique_equipment_unit_allocation'
            ),
        ]

    def __str__(self):
        return (
            f"Unit {self.unit.asset_code} "
            f"for Request #{self.request_item.request_id}"
        )

class Loan(models.Model):
    request = models.OneToOneField(BorrowRequest, on_delete=models.CASCADE, related_name='loan')
    issued_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='issued_loans')
    issued_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Loan for Request #{self.request_id}"

class ReturnRecord(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='returns')
    unit = models.ForeignKey(EquipmentUnit, on_delete=models.CASCADE)
    returned_at = models.DateTimeField(auto_now_add=True)
    condition_on_return = models.TextField()
    received_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_returns')

    def __str__(self):
        return f"Return of {self.unit.asset_code} for Loan #{self.loan_id}"

class MaintenanceRecord(models.Model):
    unit = models.ForeignKey(EquipmentUnit, on_delete=models.CASCADE, related_name='maintenance_history')
    problem_description = models.TextField()
    action_taken = models.TextField(blank=True)
    reported_at = models.DateTimeField(auto_now_add=True)
    fixed_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Maintenance for {self.unit.asset_code}"

class AuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField()

    def __str__(self):
        return f"{self.timestamp} - {self.actor} - {self.action}"

class SystemSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    @classmethod
    def get_int(cls, key, default):
        setting_value = cls.objects.filter(key=key).values_list(
            'value', flat=True
        ).first()
        try:
            return max(1, int(setting_value))
        except (TypeError, ValueError):
            return default

    def __str__(self):
        return self.key