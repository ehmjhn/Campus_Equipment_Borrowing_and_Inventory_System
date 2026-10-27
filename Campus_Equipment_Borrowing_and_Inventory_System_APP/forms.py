from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from .models import CatalogItem, UserProfile


class CatalogItemChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return (
            f"{obj.name} ({obj.category.name}) - "
            f"{obj.available_quantity} available"
        )


class BorrowRequestForm(forms.Form):
    purpose = forms.CharField(
        label="Purpose",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-textarea",
                "placeholder": "Describe how the equipment will be used...",
            }
        ),
        max_length=2000,
    )
    return_date = forms.DateField(
        label="Requested return date",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-input"}),
    )

    def __init__(
        self,
        *args,
        catalog_items,
        max_quantity,
        max_loan_duration_days,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.max_loan_duration_days = max_loan_duration_days

        for position in range(1, 4):
            self.fields[f"item_{position}"] = CatalogItemChoiceField(
                queryset=catalog_items,
                required=position == 1,
                label=f"Item {position}",
                empty_label="Select equipment",
                widget=forms.Select(attrs={"class": "form-select"}),
            )
            self.fields[f"quantity_{position}"] = forms.IntegerField(
                required=False,
                min_value=1,
                max_value=max_quantity,
                label="Quantity",
                widget=forms.NumberInput(
                    attrs={
                        "class": "form-input",
                        "min": 1,
                        "max": max_quantity,
                        "placeholder": "Qty",
                    }
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        requested_items = []
        seen_item_ids = set()

        for position in range(1, 4):
            item = cleaned_data.get(f"item_{position}")
            quantity = cleaned_data.get(f"quantity_{position}")

            if item is None:
                if quantity is not None:
                    self.add_error(
                        f"quantity_{position}",
                        "Select an item for this quantity.",
                    )
                continue

            if item.pk in seen_item_ids:
                self.add_error(
                    f"item_{position}",
                    "Choose a different item; each item can only appear once.",
                )
                continue

            seen_item_ids.add(item.pk)

            if quantity is None:
                self.add_error(
                    f"quantity_{position}",
                    "Enter a quantity for the selected item.",
                )
                continue

            requested_items.append((item, quantity))

        if not requested_items:
            self.add_error("item_1", "Select at least one item.")

        return_date = cleaned_data.get("return_date")
        if return_date:
            today = timezone.localdate()
            if return_date <= today:
                self.add_error("return_date", "The return date must be in the future.")
            elif return_date > today + timedelta(
                days=self.max_loan_duration_days
            ):
                self.add_error(
                    "return_date",
                    (
                        "The return date cannot be more than "
                        f"{self.max_loan_duration_days} days from today."
                    ),
                )

        cleaned_data["requested_items"] = requested_items
        return cleaned_data

class UserProfileForm(forms.ModelForm):

    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = UserProfile
        fields = ['contact_number']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
        self.fields['first_name'].widget.attrs.update(
            {"class": "form-input", "autocomplete": "given-name"}
        )
        self.fields['last_name'].widget.attrs.update(
            {"class": "form-input", "autocomplete": "family-name"}
        )
        self.fields['contact_number'].widget.attrs.update(
            {"class": "form-input", "autocomplete": "tel", "placeholder": "Optional contact number"}
        )


class RegisterForm(UserCreationForm):
    """Public self-registration for basic users.

    The role and activation flags are deliberately not form fields, so a
    posted ``role`` or ``is_active`` value is ignored. New accounts are always
    created as active basic users.
    """

    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=False)
    contact_number = forms.CharField(max_length=15, required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "username": "Choose a username",
            "first_name": "First name",
            "last_name": "Last name",
            "email": "you@school.edu (optional)",
            "contact_number": "Optional contact number",
            "password1": "Create a password",
            "password2": "Repeat the password",
        }
        autocomplete = {
            "username": "username",
            "first_name": "given-name",
            "last_name": "family-name",
            "email": "email",
            "contact_number": "tel",
            "password1": "new-password",
            "password2": "new-password",
        }
        for name, field in self.fields.items():
            attrs = {"class": "form-input"}
            if name in placeholders:
                attrs["placeholder"] = placeholders[name]
            if name in autocomplete:
                attrs["autocomplete"] = autocomplete[name]
            field.widget.attrs.update(attrs)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.is_staff = False
        user.is_superuser = False

        if commit:
            # Saving the user triggers the post_save signal that creates the
            # profile; it is then completed with the registration details.
            user.save()
            profile = user.profile
            profile.role = UserProfile.BASIC_USER
            profile.is_active = True
            profile.contact_number = self.cleaned_data["contact_number"]
            profile.save(
                update_fields=["role", "is_active", "contact_number"]
            )

        return user
