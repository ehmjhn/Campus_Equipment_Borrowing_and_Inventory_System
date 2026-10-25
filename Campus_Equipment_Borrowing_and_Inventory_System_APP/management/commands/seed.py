import random
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction
from Campus_Equipment_Borrowing_and_Inventory_System_APP.models import (
    UserProfile, Category, CatalogItem, EquipmentUnit, BorrowRequest,
    RequestItem, UnitAllocation, Loan, ReturnRecord, MaintenanceRecord,
    AuditLog, SystemSetting
)


class Command(BaseCommand):
    help = 'Seeds the database with fictional data meeting project requirements.'

    def handle(self, *args, **kwargs):
        with transaction.atomic():
            self.clear_existing_data()
            self.stdout.write("Previous data cleared.")

            SystemSetting.objects.update_or_create(key="max_loan_duration_days", defaults={"value": "7"})
            SystemSetting.objects.update_or_create(key="max_quantity", defaults={"value": "3"})

            admin = self.create_users()
            items_map, units_list = self.create_inventory()

            # 22 requests covering every workflow state that has data:
            # Pending, Approved, Rejected, Cancelled, Issued, Partially Returned,
            # and Returned. Overdue loans are computed from past due dates.
            self.create_pending_requests(items_map)
            self.create_approved_requests(items_map, units_list, admin)
            self.create_rejected_requests(items_map, admin)
            self.create_cancelled_requests(items_map)
            self.create_issued_loans(items_map, units_list, admin)  # 4 Loans (2 normal, 2 overdue)
            self.create_partially_returned_loans(items_map, units_list, admin)  # 2 Loans
            self.create_fully_returned_loans(items_map, units_list, admin)  # 2 Loans

            self.create_standalone_maintenance(units_list, admin)
            self.retire_one_unit(units_list, admin)

            self.stdout.write(self.style.SUCCESS("Database successfully seeded!"))
            self.stdout.write(f"  Categories: {Category.objects.count()}")
            self.stdout.write(f"  Catalog items: {CatalogItem.objects.count()}")
            self.stdout.write(f"  Physical units: {EquipmentUnit.objects.count()}")
            self.stdout.write(f"  Requests: {BorrowRequest.objects.count()}")
            self.stdout.write(f"  Loans: {Loan.objects.count()}")
            self.stdout.write(f"  Maintenance records: {MaintenanceRecord.objects.count()}")
            self.stdout.write(f"  Audit entries: {AuditLog.objects.count()}")
            self.stdout.write("Admin: admin / admin123")
            self.stdout.write("Users: user1 to user8 / user123")

    def clear_existing_data(self):
        MaintenanceRecord.objects.all().delete()
        ReturnRecord.objects.all().delete()
        Loan.objects.all().delete()
        UnitAllocation.objects.all().delete()
        RequestItem.objects.all().delete()
        BorrowRequest.objects.all().delete()
        EquipmentUnit.objects.all().delete()
        CatalogItem.objects.all().delete()
        Category.objects.all().delete()
        AuditLog.objects.all().delete()
        UserProfile.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

        # Profiles are normally created by the post_save signal. Existing
        # superusers were preserved above, so make sure they still have one.
        for user in User.objects.all():
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "role": (
                        UserProfile.ADMIN
                        if user.is_superuser
                        else UserProfile.BASIC_USER
                    ),
                },
            )

    def create_users(self):
        admin_user = User.objects.create_user(username='admin', password='admin123', first_name='System',
                                              last_name='Admin')
        admin_profile = admin_user.profile
        admin_profile.role = UserProfile.ADMIN
        admin_profile.is_active = True
        admin_profile.save(update_fields=["role", "is_active"])

        for i in range(1, 9):
            User.objects.create_user(username=f'user{i}', password='user123', first_name='Basic',
                                     last_name=f'User {i}')

        return admin_user

    def create_inventory(self):
        categories_data = [
            ("Audiovisual", "Projectors and audio equipment"),
            ("Computing", "Laptops and tablets"),
            ("Laboratory", "Science and measurement tools")
        ]

        catalog_data = {
            "Audiovisual": ["1080p Projector", "Wireless PA System"],
            "Computing": ["Windows Laptop", "iPad Pro"],
            "Laboratory": ["Digital Microscope", "Oscilloscope"]
        }

        items_map = {}
        units_list = []
        unit_counter = 1

        for cat_name, desc in categories_data:
            cat = Category.objects.create(name=cat_name, description=desc)
            for item_name in catalog_data[cat_name]:
                item = CatalogItem.objects.create(category=cat, name=item_name,
                                                  description=f"{item_name} standard unit")
                items_map[item_name] = item

                # 4 units per item = 24 units total (Comfortably satisfies the "18 minimum" requirement)
                for _ in range(4):
                    u = EquipmentUnit.objects.create(
                        catalog_item=item,
                        asset_code=f"AST-{unit_counter:04d}",
                        condition="Good",
                        status=EquipmentUnit.AVAILABLE,
                        acquisition_date=timezone.now().date() - timedelta(days=random.randint(100, 500))
                    )
                    units_list.append(u)
                    unit_counter += 1

        return items_map, units_list

    def get_random_user(self):
        return User.objects.filter(profile__role=UserProfile.BASIC_USER).order_by('?').first()

    def _create_base_request(self, items_map, status, days_offset, units_list=None):
        user = self.get_random_user()
        req = BorrowRequest.objects.create(
            user=user,
            purpose=f"Academic purpose for {status}",
            return_date=timezone.now().date() + timedelta(days=days_offset),
            status=status
        )

        # If units_list is provided, ONLY pick items that have available stock to prevent StopIteration errors
        if units_list is not None:
            available_items = list({u.catalog_item for u in units_list if u.status == EquipmentUnit.AVAILABLE})
            valid_items = available_items
        else:
            valid_items = list(items_map.values())

        num_items = min(random.randint(1, 2), len(valid_items))
        chosen_items = random.sample(valid_items, num_items) if num_items > 0 else []

        for item in chosen_items:
            RequestItem.objects.create(request=req, catalog_item=item, quantity=1)
        return req

    def create_pending_requests(self, items_map):
        for _ in range(4):
            self._create_base_request(items_map, BorrowRequest.PENDING, 3)

    def create_rejected_requests(self, items_map, admin):
        for _ in range(4):
            req = self._create_base_request(items_map, BorrowRequest.REJECTED, 3)
            req.admin_remarks = "Invalid purpose."
            req.save()
            AuditLog.objects.create(
                actor=admin,
                action="REQUEST_REJECTED",
                details=f"Rejected request #{req.pk}. Reason: Invalid purpose.",
            )

    def create_cancelled_requests(self, items_map):
        for _ in range(4):
            self._create_base_request(items_map, BorrowRequest.CANCELLED, 3)

    def create_approved_requests(self, items_map, units_list, admin):
        """Requests waiting for release: units are reserved but not issued."""
        for _ in range(2):
            req = self._create_base_request(items_map, BorrowRequest.APPROVED, 3, units_list)
            self._reserve_units(req, units_list, admin)

    def _first_available_unit(self, units_list, catalog_item):
        for unit in units_list:
            if unit.catalog_item_id == catalog_item.pk and unit.status == EquipmentUnit.AVAILABLE:
                return unit

        raise CommandError(
            f"No available unit left for '{catalog_item.name}'. "
            "Reduce the seeded request volume."
        )

    def _reserve_units(self, req, units_list, admin):
        reserved_codes = []
        for r_item in req.items.all():
            unit = self._first_available_unit(units_list, r_item.catalog_item)
            unit.status = EquipmentUnit.RESERVED
            unit.save(update_fields=["status"])
            UnitAllocation.objects.create(request_item=r_item, unit=unit)
            reserved_codes.append(unit.asset_code)

        AuditLog.objects.create(
            actor=admin,
            action="REQUEST_APPROVED",
            details=(
                f"Approved request #{req.pk}. Reserved asset codes: "
                f"{', '.join(reserved_codes)}."
            ),
        )

    def _allocate_and_issue(self, req, units_list, admin, days_ago_issued):
        issued_codes = []
        for r_item in req.items.all():
            unit = self._first_available_unit(units_list, r_item.catalog_item)
            unit.status = EquipmentUnit.ISSUED
            unit.save(update_fields=["status"])
            UnitAllocation.objects.create(request_item=r_item, unit=unit)
            issued_codes.append(unit.asset_code)

        loan = Loan.objects.create(request=req, issued_by=admin)
        Loan.objects.filter(pk=loan.pk).update(issued_at=timezone.now() - timedelta(days=days_ago_issued))
        AuditLog.objects.create(
            actor=admin,
            action="LOAN_ISSUED",
            details=(
                f"Issued request #{req.pk} as loan #{loan.pk}. "
                f"Due date: {req.return_date.isoformat()}. "
                f"Asset codes: {', '.join(issued_codes)}."
            ),
        )
        return loan

    def create_issued_loans(self, items_map, units_list, admin):
        # 2 Normal active loans
        for _ in range(2):
            req = self._create_base_request(items_map, BorrowRequest.ISSUED, 3, units_list)
            self._allocate_and_issue(req, units_list, admin, 1)

        # 2 Overdue loans
        for _ in range(2):
            req = self._create_base_request(items_map, BorrowRequest.ISSUED, -2, units_list)  # Due 2 days ago
            self._allocate_and_issue(req, units_list, admin, 5)

    def create_partially_returned_loans(self, items_map, units_list, admin):
        # 2 Partially returned loans
        for _ in range(2):
            req = self._create_base_request(items_map, BorrowRequest.PARTIALLY_RETURNED, 2, units_list)

            # Ensure it has exactly 2 items so we can return 1 and keep 1 outstanding
            if req.items.count() == 1:
                available_items = list({u.catalog_item for u in units_list if u.status == EquipmentUnit.AVAILABLE})
                existing_item = req.items.first().catalog_item
                other_items = [i for i in available_items if i != existing_item]
                if other_items:
                    RequestItem.objects.create(request=req, catalog_item=other_items[0], quantity=1)

            loan = self._allocate_and_issue(req, units_list, admin, 3)

            # Return the first unit
            alloc = req.items.first().allocations.first()
            unit = alloc.unit
            unit.status = EquipmentUnit.AVAILABLE
            unit.save()
            ReturnRecord.objects.create(loan=loan, unit=unit, condition_on_return="Good", received_by=admin)
            alloc.release(UnitAllocation.RETURNED)

    def create_fully_returned_loans(self, items_map, units_list, admin):
        # 2 Fully returned loans. One will trigger a maintenance record.
        for i in range(2):
            req = self._create_base_request(items_map, BorrowRequest.RETURNED, -1, units_list)
            loan = self._allocate_and_issue(req, units_list, admin, 5)

            for r_item in req.items.all():
                alloc = r_item.allocations.first()
                unit = alloc.unit

                if i == 0:  # Damaged return triggers maintenance
                    unit.status = EquipmentUnit.MAINTENANCE
                    unit.condition = "Damaged"
                    unit.save()
                    ReturnRecord.objects.create(loan=loan, unit=unit, condition_on_return="Damaged: Screen cracked",
                                                received_by=admin)
                    alloc.release(UnitAllocation.RETURNED)
                    MaintenanceRecord.objects.create(
                        unit=unit, problem_description="Screen cracked upon return", handled_by=admin,
                        reported_at=timezone.now()
                    )
                else:  # Good return
                    unit.status = EquipmentUnit.AVAILABLE
                    unit.save()
                    ReturnRecord.objects.create(loan=loan, unit=unit, condition_on_return="Good", received_by=admin)
                    alloc.release(UnitAllocation.RETURNED)

    def create_standalone_maintenance(self, units_list, admin):
        available_units = [u for u in units_list if u.status == EquipmentUnit.AVAILABLE]

        # 1 Open Maintenance record
        u1 = available_units[0]
        u1.status = EquipmentUnit.MAINTENANCE
        u1.save()
        MaintenanceRecord.objects.create(unit=u1, problem_description="Battery failing", handled_by=admin)

        # 2 Closed Maintenance records
        u2 = available_units[1]
        m1 = MaintenanceRecord.objects.create(unit=u2, problem_description="Loose hinge",
                                              action_taken="Tightened screws", handled_by=admin)
        MaintenanceRecord.objects.filter(pk=m1.pk).update(fixed_at=timezone.now())

        u3 = available_units[2]
        m2 = MaintenanceRecord.objects.create(unit=u3, problem_description="Software glitch",
                                              action_taken="Factory reset", handled_by=admin)
        MaintenanceRecord.objects.filter(pk=m2.pk).update(fixed_at=timezone.now())

        AuditLog.objects.create(
            actor=admin,
            action="MAINTENANCE_OPENED",
            details=f"Opened maintenance record for asset {u1.asset_code}. Problem: Battery failing.",
        )

    def retire_one_unit(self, units_list, admin):
        """Seed the fifth inventory state so every status is demonstrable."""
        unit = next((u for u in units_list if u.status == EquipmentUnit.AVAILABLE), None)

        if unit is None:
            return

        unit.status = EquipmentUnit.RETIRED
        unit.condition = "Retired: beyond economical repair"
        unit.save(update_fields=["status", "condition"])

        AuditLog.objects.create(
            actor=admin,
            action="EQUIPMENT_UNIT_RETIRED",
            details=f"Retired equipment unit {unit.asset_code} from status 'Available'.",
        )
