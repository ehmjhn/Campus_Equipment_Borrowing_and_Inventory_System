from django.apps import AppConfig


class CampusEquipmentBorrowingAndInventorySystemAppConfig(AppConfig):
    name = 'Campus_Equipment_Borrowing_and_Inventory_System_APP'

    def ready(self):
        # Registers the post_save handler that creates UserProfile records.
        from . import signals  # noqa: F401
