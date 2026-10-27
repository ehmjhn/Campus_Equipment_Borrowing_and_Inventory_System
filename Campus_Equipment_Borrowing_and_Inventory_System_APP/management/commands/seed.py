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


# Demo accounts follow the credential rules agreed for the project:
#   username -> initials of every given name, "." + surname (lower case, no spaces)
#   email    -> GivenName.Surname@bulsu.edu.ph (spaces removed)
#   password -> alab_<surname>.123
# The last field marks the showcase account used by the documentation and the
# screenshot walkthroughs; it receives one request in every lifecycle state.
DEMO_ACCOUNTS = (
    ("Ian Joshua", "Lizano", UserProfile.ADMIN, False),
    ("Maria Clara", "Santos", UserProfile.ADMIN, False),
    ("Jhon Emmanuele", "Alcanices", UserProfile.BASIC_USER, True),
    ("Jerome", "San Pedro", UserProfile.BASIC_USER, False),
    ("Alexander", "Azotes", UserProfile.BASIC_USER, False),
    ("Marc Renzo", "Bulaong", UserProfile.BASIC_USER, False),
    ("Daniel", "Alejandrino", UserProfile.BASIC_USER, False),
    ("Patricia Mae", "Reyes", UserProfile.BASIC_USER, False),
    ("Kyle Adrian", "Mendoza", UserProfile.BASIC_USER, False),
    ("Bea Nicole", "Garcia", UserProfile.BASIC_USER, False),
)

CONTACT_NUMBER_BASE = 9876543210


def demo_username(first_name, last_name):
    initials = "".join(part[0] for part in first_name.split())
    return f"{initials}.{last_name.replace(' ', '')}".lower()


def demo_email(first_name, last_name):
    return f"{first_name.replace(' ', '')}.{last_name.replace(' ', '')}@bulsu.edu.ph"


def demo_password(last_name):
    return f"alab_{last_name.replace(' ', '').lower()}.123"


class Command(BaseCommand):
    help = 'Seeds the database with the demo accounts and dataset for the project.'

    def handle(self, *args, **kwargs):
        # Deterministic demo data: the same command must produce the same
        # counts on every machine for the documentation and defense.
        random.seed(401)

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
            self.stdout.write("")
            self.stdout.write("Demo accounts (role / username / password / email / contact):")
            for account, (_first, last, role, showcase) in zip(self.users, DEMO_ACCOUNTS):
                marker = " *" if showcase else ""
                self.stdout.write(
                    f"  {role:<10} {account.username:<16} "
                    f"{demo_password(last):<23} {account.email:<38} "
                    f"{account.profile.contact_number}{marker}"
                )

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
        """Create the documented demo accounts and return the primary admin."""
        self.users = []
        self.basic_users = []
        self.admin = None
        self.demo_user = None
        self._user_cursor = 0

        for index, (first, last, role, showcase) in enumerate(DEMO_ACCOUNTS):
            account = User.objects.create_user(
                username=demo_username(first, last),
                email=demo_email(first, last),
                password=demo_password(last),
                first_name=first,
                last_name=last,
            )

            profile = account.profile
            profile.role = role
            profile.is_active = True
            profile.contact_number = f"0{CONTACT_NUMBER_BASE + index}"
            profile.save(update_fields=["role", "is_active", "contact_number"])

            self.users.append(account)

            if role == UserProfile.ADMIN and self.admin is None:
                self.admin = account
            elif role == UserProfile.BASIC_USER:
                self.basic_users.append(account)

            if showcase:
                self.demo_user = account

        return self.admin

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

    def _next_user(self):
        """Round-robin owner so every demo account gets a share of the history.

        A random owner would make the screenshots and the documented walkthrough
        non-reproducible, and could leave the showcase account with no requests.
        """
        if not self.basic_users:
            raise CommandError("No basic user accounts exist to own seeded requests.")

        user = self.basic_users[self._user_cursor % len(self.basic_users)]
        self._user_cursor += 1
        return user

    def _create_base_request(self, items_map, status, days_offset, units_list=None, user=None):
        user = user or self._next_user()
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
        # The showcase account owns the first one so its history demonstrates
        # the cancellation state as well.
        for i in range(4):
            self._create_base_request(
                items_map,
                BorrowRequest.CANCELLED,
                3,
                user=self.demo_user if i == 0 else None,
            )

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
        # The showcase account owns the first one so the documented walkthrough
        # can show a request in every lifecycle state.
        for i in range(2):
            req = self._create_base_request(
                items_map,
                BorrowRequest.RETURNED,
                -1,
                units_list,
                user=self.demo_user if i == 0 else None,
            )
            loan = self._allocate_and_issue(req, units_list, admin, 5)

            for index, r_item in enumerate(req.items.all()):
                alloc = r_item.allocations.first()
                unit = alloc.unit

                # Exactly one damaged unit, so the dataset always documents
                # four maintenance records regardless of how many items the
                # random request ended up containing.
                if i == 0 and index == 0:
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
