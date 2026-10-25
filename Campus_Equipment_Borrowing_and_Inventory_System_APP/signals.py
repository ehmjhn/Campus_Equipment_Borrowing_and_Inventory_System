"""Signals that keep authentication users and campus profiles in sync.

Every `User` gets exactly one `UserProfile`. Superusers are treated as campus
administrators so that `createsuperuser` is enough to bootstrap the custom
`/manage/` area; everyone else defaults to the basic-user role.

Note: registration never trusts a posted role. `views.register` uses the
`RegisterForm`, which does not expose the role field at all, and
`UserProfileForm` only exposes personal details.
"""

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile

User = get_user_model()


@receiver(post_save, sender=User, dispatch_uid="ensure_user_profile")
def ensure_user_profile(sender, instance, created, **kwargs):
    if not created:
        return

    UserProfile.objects.get_or_create(
        user=instance,
        defaults={
            "role": (
                UserProfile.ADMIN
                if instance.is_superuser
                else UserProfile.BASIC_USER
            ),
        },
    )
