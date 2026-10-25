import csv
from datetime import timedelta
from functools import wraps

from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.dateparse import parse_date

from .models import (
    UserProfile,
    EquipmentUnit,
    BorrowRequest,
    RequestItem,
    UnitAllocation,
    Loan,
    AuditLog,
    Category,
    CatalogItem,
    SystemSetting,
    ReturnRecord,
    MaintenanceRecord
)
from .forms import BorrowRequestForm, RegisterForm, UserProfileForm

User = get_user_model()


def admin_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            return HttpResponseForbidden(
                "You do not have permission to access this page."
            )

        if (
            not request.user.is_active
            or not profile.is_active
            or profile.role != UserProfile.ADMIN
        ):
            return HttpResponseForbidden(
                "You do not have permission to access this page."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def basic_user_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            return HttpResponseForbidden(
                "You do not have permission to access this page."
            )

        if (
            not request.user.is_active
            or not profile.is_active
            or profile.role != UserProfile.BASIC_USER
        ):
            return HttpResponseForbidden(
                "You do not have permission to access this page."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def role_redirect(request):
    """Send each signed-in user to the area that matches their role."""
    if not request.user.is_authenticated:
        return redirect("login")

    profile = getattr(request.user, "profile", None)

    if (
        profile is not None
        and profile.is_active
        and profile.role == UserProfile.ADMIN
    ):
        return redirect("admin_dashboard")

    return redirect("portal_home")


def register(request):
    """Public registration for the basic-user role only."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(
                request,
                "Account created. Browse the catalog to submit a request.",
            )
            return redirect("portal_home")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form})


@admin_required
def admin_dashboard(request):
    date_from_text = request.GET.get("date_from", "").strip()
    date_to_text = request.GET.get("date_to", "").strip()
    date_from = parse_date(date_from_text) if date_from_text else None
    date_to = parse_date(date_to_text) if date_to_text else None
    filter_is_valid = (
        (not date_from_text or date_from is not None)
        and (not date_to_text or date_to is not None)
        and not (date_from and date_to and date_from > date_to)
    )

    if not filter_is_valid:
        messages.error(request, "Enter a valid date range with the start date on or before the end date.")
        date_from = None
        date_to = None

    available_units_count = EquipmentUnit.objects.filter(
        status=EquipmentUnit.AVAILABLE,
        catalog_item__is_archived=False,
        catalog_item__category__is_archived=False,
    ).count()

    pending_requests_count = BorrowRequest.objects.filter(
        status=BorrowRequest.PENDING
    ).count()

    active_loans_count = Loan.objects.filter(
        request__status__in=[
            BorrowRequest.ISSUED,
            BorrowRequest.PARTIALLY_RETURNED,
        ]
    ).count()

    overdue_loans_count = Loan.objects.filter(
        request__status__in=[
            BorrowRequest.ISSUED,
            BorrowRequest.PARTIALLY_RETURNED,
        ],
        request__return_date__lt=timezone.now().date(),
    ).count()

    loans = (
        Loan.objects.select_related("request", "request__user", "issued_by")
        .prefetch_related(
            "request__items__catalog_item",
            "request__items__allocations__unit",
        )
    )
    allocations = UnitAllocation.objects.select_related(
        "request_item__request__loan",
        "request_item__catalog_item__category",
        "unit",
    )
    if date_from:
        loans = loans.filter(issued_at__date__gte=date_from)
        allocations = allocations.filter(
            request_item__request__loan__issued_at__date__gte=date_from
        )
    if date_to:
        loans = loans.filter(issued_at__date__lte=date_to)
        allocations = allocations.filter(
            request_item__request__loan__issued_at__date__lte=date_to
        )

    monthly_issued = list(
        loans.annotate(month=TruncMonth("issued_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("-month")[:12]
    )
    monthly_issued.reverse()
    category_usage = list(
        allocations.values("request_item__catalog_item__category__name")
        .annotate(count=Count("id"))
        .order_by("-count", "request_item__catalog_item__category__name")[:10]
    )
    max_monthly_issued = max(
        (row["count"] for row in monthly_issued),
        default=0,
    )
    max_category_usage = max(
        (row["count"] for row in category_usage),
        default=0,
    )

    context = {
        "available_units": available_units_count,
        "pending_requests": pending_requests_count,
        "active_loans": active_loans_count,
        "overdue_loans": overdue_loans_count,
        "monthly_issued": monthly_issued,
        "category_usage": category_usage,
        "max_monthly_issued": max_monthly_issued,
        "max_category_usage": max_category_usage,
        "loan_report_rows": list(
            loans.order_by("-issued_at", "-id")[:50]
        ),
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
    }

    return render(request, "manage/dashboard.html", context)


@admin_required
def dashboard_report_csv(request):
    date_from_text = request.GET.get("date_from", "").strip()
    date_to_text = request.GET.get("date_to", "").strip()
    date_from = parse_date(date_from_text) if date_from_text else None
    date_to = parse_date(date_to_text) if date_to_text else None
    if (
        (date_from_text and date_from is None)
        or (date_to_text and date_to is None)
        or (date_from and date_to and date_from > date_to)
    ):
        return HttpResponseBadRequest("Provide a valid date range.")

    loans = Loan.objects.select_related(
        "request__user",
        "request",
        "issued_by",
    ).prefetch_related(
        "request__items__catalog_item__category",
        "request__items__allocations__unit",
    ).order_by("issued_at", "id")
    if date_from:
        loans = loans.filter(issued_at__date__gte=date_from)
    if date_to:
        loans = loans.filter(issued_at__date__lte=date_to)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="equipment-usage-report.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Loan ID",
            "Issued At",
            "Borrower",
            "Issued By",
            "Due Date",
            "Request Status",
            "Purpose",
            "Category",
            "Catalog Item",
            "Asset Code",
        ]
    )

    def csv_value(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return f"'{value}"
        return value

    for loan in loans:
        for request_item in loan.request.items.all():
            for allocation in request_item.allocations.all():
                writer.writerow(
                    [
                        loan.pk,
                        timezone.localtime(loan.issued_at).isoformat(),
                        csv_value(loan.request.user.get_username()),
                        csv_value(loan.issued_by.get_username()),
                        loan.request.return_date.isoformat(),
                        loan.request.status,
                        csv_value(loan.request.purpose),
                        csv_value(request_item.catalog_item.category.name),
                        csv_value(request_item.catalog_item.name),
                        csv_value(allocation.unit.asset_code),
                    ]
                )

    AuditLog.objects.create(
        actor=request.user,
        action="REPORT_EXPORTED",
        details=(
            "Exported equipment usage report"
            f"{f' from {date_from.isoformat()}' if date_from else ''}"
            f"{f' through {date_to.isoformat()}' if date_to else ''}."
        ),
    )
    return response


def _csv_safe(value):
    """Prevent spreadsheet formula injection in exported cells."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _overdue_loan_rows(date_from=None, date_to=None):
    """Return active loans that still have units out past their due date."""
    today = timezone.localdate()
    loans = (
        Loan.objects
        .filter(
            request__status__in=[
                BorrowRequest.ISSUED,
                BorrowRequest.PARTIALLY_RETURNED,
            ],
            request__return_date__lt=today,
        )
        .select_related("request", "request__user", "issued_by")
        .prefetch_related(
            "request__items__catalog_item",
            "request__items__allocations__unit",
            "returns__unit",
        )
        .order_by("request__return_date", "id")
    )

    if date_from:
        loans = loans.filter(issued_at__date__gte=date_from)
    if date_to:
        loans = loans.filter(issued_at__date__lte=date_to)

    rows = []
    for loan in loans:
        returned_unit_ids = {record.unit_id for record in loan.returns.all()}
        outstanding_allocations = [
            allocation
            for request_item in loan.request.items.all()
            for allocation in request_item.allocations.all()
            if allocation.unit_id not in returned_unit_ids
        ]

        if not outstanding_allocations:
            continue

        rows.append({
            "loan": loan,
            "outstanding_allocations": outstanding_allocations,
            "outstanding_count": len(outstanding_allocations),
            "overdue_days": (today - loan.request.return_date).days,
        })

    return rows


@admin_required
def overdue_report(request):
    date_from_text = request.GET.get("date_from", "").strip()
    date_to_text = request.GET.get("date_to", "").strip()
    date_from = parse_date(date_from_text) if date_from_text else None
    date_to = parse_date(date_to_text) if date_to_text else None

    filter_is_valid = (
        (not date_from_text or date_from is not None)
        and (not date_to_text or date_to is not None)
        and not (date_from and date_to and date_from > date_to)
    )
    if not filter_is_valid:
        messages.error(
            request,
            "Enter a valid date range with the start date on or before the end date.",
        )
        date_from = None
        date_to = None

    rows = _overdue_loan_rows(date_from, date_to)

    return render(
        request,
        "manage/overdue_report.html",
        {
            "rows": rows,
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
        },
    )


@admin_required
def overdue_report_csv(request):
    date_from_text = request.GET.get("date_from", "").strip()
    date_to_text = request.GET.get("date_to", "").strip()
    date_from = parse_date(date_from_text) if date_from_text else None
    date_to = parse_date(date_to_text) if date_to_text else None
    if (
        (date_from_text and date_from is None)
        or (date_to_text and date_to is None)
        or (date_from and date_to and date_from > date_to)
    ):
        return HttpResponseBadRequest("Provide a valid date range.")

    rows = _overdue_loan_rows(date_from, date_to)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="overdue-report.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Loan ID",
            "Issued At",
            "Borrower",
            "Due Date",
            "Request Status",
            "Overdue Days",
            "Outstanding Units",
            "Asset Codes",
        ]
    )

    for row in rows:
        loan = row["loan"]
        writer.writerow(
            [
                loan.pk,
                timezone.localtime(loan.issued_at).isoformat(),
                _csv_safe(loan.request.user.get_username()),
                loan.request.return_date.isoformat(),
                loan.request.status,
                row["overdue_days"],
                row["outstanding_count"],
                _csv_safe(
                    ", ".join(
                        allocation.unit.asset_code
                        for allocation in row["outstanding_allocations"]
                    )
                ),
            ]
        )

    AuditLog.objects.create(
        actor=request.user,
        action="REPORT_EXPORTED",
        details=(
            "Exported overdue loans report"
            f"{f' from {date_from.isoformat()}' if date_from else ''}"
            f"{f' through {date_to.isoformat()}' if date_to else ''}."
        ),
    )
    return response


@admin_required
def account_management(request):
    search_query = request.GET.get("q", "").strip()

    users = User.objects.all().order_by("username")

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
        )

    account_rows = []
    for account in users:
        profile, _ = UserProfile.objects.get_or_create(user=account)
        account_rows.append({
            "user": account,
            "profile": profile,
            "is_active": account.is_active and profile.is_active,
        })

    paginator = Paginator(account_rows, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "manage/accounts.html",
        {
            "page_obj": page_obj,
            "search_query": search_query,
        },
    )


@admin_required
def account_detail(request, user_id):
    account = get_object_or_404(User, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=account)

    requests_queryset = (
        BorrowRequest.objects.filter(user=account)
        .select_related("loan")
        .prefetch_related(
            "items__catalog_item__category",
            "items__allocations__unit",
            "loan__returns__unit",
        )
        .order_by("-requested_at", "-id")
    )
    page_obj = Paginator(requests_queryset, 10).get_page(
        request.GET.get("page")
    )

    history_rows = []
    for borrow_request in page_obj.object_list:
        allocations = [
            allocation
            for request_item in borrow_request.items.all()
            for allocation in request_item.allocations.all()
        ]
        history_rows.append({
            "request": borrow_request,
            "items": borrow_request.items.all(),
            "allocations": allocations,
            "loan": getattr(borrow_request, "loan", None),
        })

    return render(
        request,
        "manage/account_detail.html",
        {
            "account": account,
            "profile": profile,
            "is_active": account.is_active and profile.is_active,
            "page_obj": page_obj,
            "history_rows": history_rows,
        },
    )


@admin_required
@require_POST
def toggle_account_status(request, user_id):
    with transaction.atomic():
        account = get_object_or_404(
            User.objects.select_for_update(),
            pk=user_id,
        )

        profile, _ = UserProfile.objects.get_or_create(user=account)

        if account.pk == request.user.pk:
            messages.error(
                request,
                "You cannot change the activation status of your own account.",
            )
            return redirect("account_management")

        currently_active = account.is_active and profile.is_active

        if currently_active:
            if profile.role == UserProfile.ADMIN:
                active_admin_count = UserProfile.objects.filter(
                    role=UserProfile.ADMIN,
                    is_active=True,
                    user__is_active=True,
                ).exclude(user_id=account.pk).count()

                if active_admin_count == 0:
                    messages.error(
                        request,
                        "At least one active administrator account must remain.",
                    )
                    return redirect("account_management")

            account.is_active = False
            profile.is_active = False
            action = "ACCOUNT_DEACTIVATED"
            details = f"Deactivated account: {account.username}"
        else:
            account.is_active = True
            profile.is_active = True
            action = "ACCOUNT_ACTIVATED"
            details = f"Activated account: {account.username}"

        account.save(update_fields=["is_active"])
        profile.save(update_fields=["is_active"])

        AuditLog.objects.create(
            actor=request.user,
            action=action,
            details=details,
        )

    return redirect("account_management")


@admin_required
def category_management(request):
    search_query = request.GET.get("q", "").strip()

    categories = Category.objects.all().order_by("name")

    if search_query:
        categories = categories.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
        )

    return render(
        request,
        "manage/categories.html",
        {
            "categories": categories,
            "search_query": search_query,
        },
    )


@admin_required
@require_POST
def category_create(request):
    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()

    if not name:
        messages.error(request, "Category name is required.")
        return redirect("category_management")

    if Category.objects.filter(name__iexact=name).exists():
        messages.error(request, "This category already exists.")
        return redirect("category_management")

    category = Category.objects.create(
        name=name,
        description=description,
    )

    AuditLog.objects.create(
        actor=request.user,
        action="CATEGORY_CREATED",
        details=f"Created category: {category.name} (ID: {category.pk})",
    )

    messages.success(request, "Category created successfully.")
    return redirect("category_management")


@admin_required
@require_POST
def category_edit(request, category_id):
    category = get_object_or_404(Category, pk=category_id)

    if category.is_archived:
        messages.error(request, "Archived categories cannot be edited.")
        return redirect("category_management")

    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()

    if not name:
        messages.error(request, "Category name is required.")
        return redirect("category_management")

    duplicate_exists = Category.objects.filter(
        name__iexact=name
    ).exclude(pk=category.pk).exists()

    if duplicate_exists:
        messages.error(request, "Another category already uses this name.")
        return redirect("category_management")

    old_name = category.name

    category.name = name
    category.description = description
    category.save(update_fields=["name", "description"])

    AuditLog.objects.create(
        actor=request.user,
        action="CATEGORY_UPDATED",
        details=(
            f"Updated category ID {category.pk}: "
            f"'{old_name}' to '{category.name}'."
        ),
    )

    messages.success(request, "Category updated successfully.")
    return redirect("category_management")


@admin_required
@require_POST
def category_archive(request, category_id):
    category = get_object_or_404(Category, pk=category_id)

    if category.is_archived:
        messages.info(request, "This category is already archived.")
        return redirect("category_management")

    active_items_exist = CatalogItem.objects.filter(
        category=category,
        is_archived=False,
    ).exists()

    if active_items_exist:
        messages.error(
            request,
            (
                f"Cannot archive category '{category.name}' because it "
                "still contains active catalog items. Archive or move "
                "those items first."
            ),
        )
        return redirect("category_management")

    with transaction.atomic():
        category.is_archived = True
        category.save(update_fields=["is_archived"])

        AuditLog.objects.create(
            actor=request.user,
            action="CATEGORY_ARCHIVED",
            details=(
                f"Archived category: {category.name} "
                f"(ID: {category.pk})"
            ),
        )

    messages.success(
        request,
        f"Category '{category.name}' archived successfully.",
    )
    return redirect("category_management")

@admin_required
def catalog_item_management(request):
    search_query = request.GET.get("q", "").strip()

    items = CatalogItem.objects.select_related("category").order_by(
        "category__name", "name"
    )

    if search_query:
        items = items.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(category__name__icontains=search_query)
        )

    return render(
        request,
        "manage/catalog_items.html",
        {
            "items": items,
            "search_query": search_query,
            "active_categories": Category.objects.filter(
                is_archived=False
            ).order_by("name"),
        },
    )

def _inventory_status_summary():
    """Per catalog item unit counts for the reconciliation panel."""
    statuses = [value for value, _ in EquipmentUnit.STATUS_CHOICES]
    counts = {}

    for row in (
        EquipmentUnit.objects
        .values("catalog_item_id", "status")
        .annotate(total=Count("id"))
    ):
        counts.setdefault(row["catalog_item_id"], {})[row["status"]] = row["total"]

    rows = []
    items = (
        CatalogItem.objects
        .select_related("category")
        .order_by("category__name", "name")
    )
    for item in items:
        item_counts = counts.get(item.pk, {})
        rows.append(
            {
                "item": item,
                "total": sum(item_counts.values()),
                "statuses": [
                    {"label": status, "count": item_counts.get(status, 0)}
                    for status in statuses
                ],
            }
        )

    return rows


def _inventory_anomalies():
    """Detect units whose status disagrees with allocation/loan records."""
    allocated_unit_ids = UnitAllocation.objects.filter(
        released_at__isnull=True,
    ).values_list("unit_id", flat=True)

    orphaned_reserved = (
        EquipmentUnit.objects
        .filter(status=EquipmentUnit.RESERVED)
        .exclude(pk__in=allocated_unit_ids)
        .select_related("catalog_item")
    )

    stale_allocations = (
        UnitAllocation.objects
        .filter(
            released_at__isnull=True,
            request_item__request__status__in=[
                BorrowRequest.PENDING,
                BorrowRequest.APPROVED,
            ]
        )
        .exclude(unit__status=EquipmentUnit.RESERVED)
        .select_related("unit", "request_item__request")
    )

    issued_without_active_loan = (
        EquipmentUnit.objects
        .filter(status=EquipmentUnit.ISSUED)
        .exclude(
            pk__in=UnitAllocation.objects.filter(
                released_at__isnull=True,
                request_item__request__status__in=[
                    BorrowRequest.ISSUED,
                    BorrowRequest.PARTIALLY_RETURNED,
                ]
            ).values("unit_id")
        )
        .select_related("catalog_item")
    )

    return {
        "orphaned_reserved": list(orphaned_reserved),
        "stale_allocations": list(stale_allocations),
        "issued_without_active_loan": list(issued_without_active_loan),
    }


@admin_required
def physical_units_management(request):
    category_filter = request.GET.get("category", "").strip()
    item_filter = request.GET.get("item", "").strip()
    status_filter = request.GET.get("status", "").strip()

    active_catalog_items = (
        CatalogItem.objects
        .filter(
            is_archived=False,
            category__is_archived=False,
        )
        .select_related("category")
        .order_by("name")
    )

    equipment_units = (
        EquipmentUnit.objects
        .select_related(
            "catalog_item",
            "catalog_item__category",
        )
        .order_by(
            "catalog_item__name",
            "asset_code",
        )
    )

    if category_filter.isdigit():
        equipment_units = equipment_units.filter(
            catalog_item__category_id=int(category_filter)
        )
    else:
        category_filter = ""

    if item_filter.isdigit():
        equipment_units = equipment_units.filter(
            catalog_item_id=int(item_filter)
        )
    else:
        item_filter = ""

    valid_statuses = {value for value, _ in EquipmentUnit.STATUS_CHOICES}
    if status_filter in valid_statuses:
        equipment_units = equipment_units.filter(status=status_filter)
    else:
        status_filter = ""

    context = {
        "active_catalog_items": active_catalog_items,
        "equipment_units": equipment_units,
        "filter_categories": Category.objects.order_by("name"),
        "filter_items": CatalogItem.objects.select_related("category").order_by(
            "category__name",
            "name",
        ),
        "category_filter": category_filter,
        "item_filter": item_filter,
        "status_filter": status_filter,
        "reconciliation_rows": _inventory_status_summary(),
        "anomalies": _inventory_anomalies(),
        "unit_statuses": [
            label for _, label in EquipmentUnit.STATUS_CHOICES
        ],
    }

    return render(
        request,
        "manage/physical_units.html",
        context,
    )

@admin_required
@require_POST
def catalog_item_create(request):
    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()
    category_id = request.POST.get("category")

    if not name or not category_id:
        messages.error(request, "Item name and category are required.")
        return redirect("catalog_item_management")

    category = get_object_or_404(
        Category,
        pk=category_id,
        is_archived=False,
    )

    if CatalogItem.objects.filter(
        category=category,
        name__iexact=name,
        is_archived=False,
    ).exists():
        messages.error(
            request,
            "An active item with this name already exists in that category.",
        )
        return redirect("catalog_item_management")

    item = CatalogItem.objects.create(
        category=category,
        name=name,
        description=description,
    )

    AuditLog.objects.create(
        actor=request.user,
        action="CATALOG_ITEM_CREATED",
        details=(
            f"Created catalog item: {item.name} "
            f"in category '{category.name}' (ID: {item.pk})."
        ),
    )

    messages.success(request, "Catalog item created successfully.")
    return redirect("catalog_item_management")


@admin_required
@require_POST
def catalog_item_edit(request, item_id):
    item = get_object_or_404(CatalogItem, pk=item_id)

    if item.is_archived:
        messages.error(request, "Archived items cannot be edited.")
        return redirect("catalog_item_management")

    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()
    category_id = request.POST.get("category")

    if not name or not category_id:
        messages.error(request, "Item name and category are required.")
        return redirect("catalog_item_management")

    category = get_object_or_404(
        Category,
        pk=category_id,
        is_archived=False,
    )

    duplicate_exists = CatalogItem.objects.filter(
        category=category,
        name__iexact=name,
        is_archived=False,
    ).exclude(pk=item.pk).exists()

    if duplicate_exists:
        messages.error(
            request,
            "An active item with this name already exists in that category.",
        )
        return redirect("catalog_item_management")

    old_name = item.name
    old_category = item.category.name

    item.name = name
    item.description = description
    item.category = category
    item.save(update_fields=["name", "description", "category"])

    AuditLog.objects.create(
        actor=request.user,
        action="CATALOG_ITEM_UPDATED",
        details=(
            f"Updated catalog item ID {item.pk}: "
            f"'{old_name}' in '{old_category}' to "
            f"'{item.name}' in '{category.name}'."
        ),
    )

    messages.success(request, "Catalog item updated successfully.")
    return redirect("catalog_item_management")


@admin_required
@require_POST
def catalog_item_archive(request, item_id):
    item = get_object_or_404(CatalogItem, pk=item_id)

    if item.is_archived:
        messages.info(request, "This item is already archived.")
        return redirect("catalog_item_management")

    has_active_units = item.units.filter(
        status__in=[
            EquipmentUnit.RESERVED,
            EquipmentUnit.ISSUED,
        ]
    ).exists()

    if has_active_units:
        messages.error(
            request,
            "This item has reserved or issued units. "
            "Resolve those transactions before archiving it.",
        )
        return redirect("catalog_item_management")

    has_open_requests = BorrowRequest.objects.filter(
        items__catalog_item=item,
        status__in=[
            BorrowRequest.PENDING,
            BorrowRequest.APPROVED,
        ],
    ).exists()

    if has_open_requests:
        messages.error(
            request,
            "This item is referenced by pending or approved requests. "
            "Resolve those requests before archiving it.",
        )
        return redirect("catalog_item_management")

    with transaction.atomic():
        item.is_archived = True
        item.save(update_fields=["is_archived"])

        AuditLog.objects.create(
            actor=request.user,
            action="CATALOG_ITEM_ARCHIVED",
            details=f"Archived catalog item: {item.name} (ID: {item.pk}).",
        )

    messages.success(request, "Catalog item archived successfully.")
    return redirect("catalog_item_management")



@admin_required
@require_POST
def equipment_unit_create(request):
    catalog_item_id = request.POST.get("catalog_item")
    asset_code = request.POST.get("asset_code", "").strip()
    condition = request.POST.get("condition", "").strip()
    acquisition_date_text = request.POST.get("acquisition_date", "").strip()

    if not catalog_item_id or not asset_code or not condition or not acquisition_date_text:
        messages.error(
            request,
            "All equipment unit fields are required.",
        )
        return redirect("catalog_item_management")

    catalog_item = get_object_or_404(
        CatalogItem,
        pk=catalog_item_id,
        is_archived=False,
        category__is_archived=False,
    )

    acquisition_date = parse_date(acquisition_date_text)

    if acquisition_date is None:
        messages.error(
            request,
            "Please provide a valid acquisition date.",
        )
        return redirect("catalog_item_management")

    if EquipmentUnit.objects.filter(
        asset_code__iexact=asset_code
    ).exists():
        messages.error(
            request,
            "That asset code is already registered. Use a unique asset code.",
        )
        return redirect("catalog_item_management")

    try:
        with transaction.atomic():
            unit = EquipmentUnit.objects.create(
                catalog_item=catalog_item,
                asset_code=asset_code,
                condition=condition,
                acquisition_date=acquisition_date,
                status=EquipmentUnit.AVAILABLE,
            )

            AuditLog.objects.create(
                actor=request.user,
                action="EQUIPMENT_UNIT_REGISTERED",
                details=(
                    f"Registered equipment unit {unit.asset_code} "
                    f"for catalog item '{catalog_item.name}' "
                    f"(Unit ID: {unit.pk})."
                ),
            )

    except IntegrityError:
        messages.error(
            request,
            "That asset code is already registered. Use a unique asset code.",
        )
        return redirect("catalog_item_management")

    messages.success(
        request,
        f"Equipment unit '{unit.asset_code}' registered successfully.",
    )
    return redirect("catalog_item_management")

@admin_required
@require_POST
def equipment_unit_update(request, unit_id):
    """Update the mutable details of a physical unit.

    Asset codes are immutable on purpose: they are referenced by loans,
    returns, and audit entries, so rewriting them would break the history the
    system exists to preserve.
    """
    condition = request.POST.get("condition", "").strip()
    acquisition_date_text = request.POST.get("acquisition_date", "").strip()
    acquisition_date = (
        parse_date(acquisition_date_text) if acquisition_date_text else None
    )

    if not condition or acquisition_date is None:
        messages.error(
            request,
            "A condition description and a valid acquisition date are required.",
        )
        return redirect("physical_units_management")

    with transaction.atomic():
        unit = get_object_or_404(
            EquipmentUnit.objects.select_for_update(),
            pk=unit_id,
        )

        if unit.status == EquipmentUnit.RETIRED:
            messages.error(
                request,
                f"Asset {unit.asset_code} is retired. Restore it before editing.",
            )
            return redirect("physical_units_management")

        if unit.status in [EquipmentUnit.RESERVED, EquipmentUnit.ISSUED]:
            messages.error(
                request,
                (
                    f"Asset {unit.asset_code} is currently "
                    f"{unit.status.lower()}. Resolve the transaction before "
                    "editing its details."
                ),
            )
            return redirect("physical_units_management")

        old_condition = unit.condition
        old_acquisition_date = unit.acquisition_date

        unit.condition = condition
        unit.acquisition_date = acquisition_date
        unit.save(update_fields=["condition", "acquisition_date"])

        AuditLog.objects.create(
            actor=request.user,
            action="EQUIPMENT_UNIT_UPDATED",
            details=(
                f"Updated equipment unit {unit.asset_code} (Unit ID: {unit.pk}). "
                f"Condition: '{old_condition}' to '{unit.condition}'. "
                f"Acquisition date: {old_acquisition_date.isoformat()} to "
                f"{unit.acquisition_date.isoformat()}."
            ),
        )

    messages.success(
        request,
        f"Equipment unit '{unit.asset_code}' updated successfully.",
    )
    return redirect("physical_units_management")


@admin_required
@require_POST
def equipment_unit_retire(request, unit_id):
    """Retire a physical unit instead of deleting it (preserves history)."""
    with transaction.atomic():
        unit = get_object_or_404(
            EquipmentUnit.objects.select_for_update(),
            pk=unit_id,
        )

        if unit.status == EquipmentUnit.RETIRED:
            messages.info(
                request,
                f"Asset {unit.asset_code} is already retired.",
            )
            return redirect("physical_units_management")

        if unit.status in [EquipmentUnit.RESERVED, EquipmentUnit.ISSUED]:
            messages.error(
                request,
                (
                    f"Asset {unit.asset_code} cannot be retired while it is "
                    f"{unit.status.lower()}. Resolve the transaction first."
                ),
            )
            return redirect("physical_units_management")

        previous_status = unit.status
        unit.status = EquipmentUnit.RETIRED
        unit.save(update_fields=["status"])

        AuditLog.objects.create(
            actor=request.user,
            action="EQUIPMENT_UNIT_RETIRED",
            details=(
                f"Retired equipment unit {unit.asset_code} (Unit ID: {unit.pk}) "
                f"from status '{previous_status}'."
            ),
        )

    messages.success(request, f"Asset {unit.asset_code} retired.")
    return redirect("physical_units_management")


@admin_required
@require_POST
def equipment_unit_restore(request, unit_id):
    """Return a retired unit to the available pool."""
    with transaction.atomic():
        unit = get_object_or_404(
            EquipmentUnit.objects.select_for_update(),
            pk=unit_id,
        )

        if unit.status != EquipmentUnit.RETIRED:
            messages.error(
                request,
                f"Asset {unit.asset_code} is not retired and cannot be restored.",
            )
            return redirect("physical_units_management")

        unit.status = EquipmentUnit.AVAILABLE
        unit.save(update_fields=["status"])

        AuditLog.objects.create(
            actor=request.user,
            action="EQUIPMENT_UNIT_RESTORED",
            details=(
                f"Restored retired equipment unit {unit.asset_code} "
                f"(Unit ID: {unit.pk}) to 'Available'."
            ),
        )

    messages.success(
        request,
        f"Asset {unit.asset_code} restored to the available pool.",
    )
    return redirect("physical_units_management")


@admin_required
@require_POST
def reconcile_inventory(request):
    """Repair reserved units that no longer have an allocation.

    A unit can only be reserved through a `UnitAllocation`. When an allocation
    disappears without releasing the unit (for example, manual database edits),
    the unit is stuck as reserved and can never be borrowed again. This action
    releases exactly those orphaned units and records the outcome.
    """
    with transaction.atomic():
        allocated_unit_ids = UnitAllocation.objects.filter(
            released_at__isnull=True,
        ).values_list("unit_id", flat=True)
        orphaned_units = list(
            EquipmentUnit.objects.select_for_update().filter(
                status=EquipmentUnit.RESERVED,
            ).exclude(pk__in=allocated_unit_ids)
        )

        for unit in orphaned_units:
            unit.status = EquipmentUnit.AVAILABLE

        if orphaned_units:
            EquipmentUnit.objects.bulk_update(orphaned_units, ["status"])

        asset_codes = ", ".join(unit.asset_code for unit in orphaned_units)

        AuditLog.objects.create(
            actor=request.user,
            action="INVENTORY_RECONCILED",
            details=(
                f"Released {len(orphaned_units)} orphaned reserved unit(s). "
                f"Asset codes: {asset_codes or 'none'}."
            ),
        )

    if orphaned_units:
        messages.success(
            request,
            f"Reconciled {len(orphaned_units)} orphaned reserved unit(s).",
        )
    else:
        messages.info(
            request,
            "Inventory is consistent; no orphaned reserved units were found.",
        )

    return redirect("physical_units_management")


@admin_required
def request_review(request):
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    date_from_text = request.GET.get("date_from", "").strip()
    date_to_text = request.GET.get("date_to", "").strip()
    date_from = parse_date(date_from_text) if date_from_text else None
    date_to = parse_date(date_to_text) if date_to_text else None

    filter_is_valid = (
        (not date_from_text or date_from is not None)
        and (not date_to_text or date_to is not None)
        and not (date_from and date_to and date_from > date_to)
    )
    if not filter_is_valid:
        messages.error(
            request,
            "Enter a valid request date range with the start date on or before the end date.",
        )
        date_from = None
        date_to = None

    requests = (
        BorrowRequest.objects
        .select_related("user")
        .prefetch_related(
            "items__catalog_item",
            "items__allocations__unit",
        )
        .order_by("-requested_at", "-id")
    )

    if search_query:
        requests = requests.filter(
            Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(purpose__icontains=search_query)
            | Q(admin_remarks__icontains=search_query)
            | Q(items__catalog_item__name__icontains=search_query)
            | Q(items__catalog_item__category__name__icontains=search_query)
        ).distinct()

    valid_statuses = {
        value for value, label in BorrowRequest.STATUS_CHOICES
    }

    if status_filter in valid_statuses:
        requests = requests.filter(status=status_filter)
    else:
        status_filter = ""

    if date_from:
        requests = requests.filter(requested_at__date__gte=date_from)
    if date_to:
        requests = requests.filter(requested_at__date__lte=date_to)

    paginator = Paginator(requests, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Show the reviewer how many units are free right now, so a request is
    # never approved on stale stock information.
    available_counts = {
        row["catalog_item_id"]: row["available"]
        for row in (
            EquipmentUnit.objects
            .filter(status=EquipmentUnit.AVAILABLE)
            .values("catalog_item_id")
            .annotate(available=Count("id"))
        )
    }
    for borrow_request in page_obj.object_list:
        for request_item in borrow_request.items.all():
            request_item.available_now = available_counts.get(
                request_item.catalog_item_id,
                0,
            )

    context = {
        "page_obj": page_obj,
        "requests": page_obj.object_list,
        "search_query": search_query,
        "status_filter": status_filter,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "status_choices": BorrowRequest.STATUS_CHOICES,
    }

    return render(
        request,
        "manage/request_review.html",
        context,
    )

@admin_required
@require_POST
def request_approve(request, request_id):
    remarks = request.POST.get("admin_remarks", "").strip()

    try:
        with transaction.atomic():
            borrow_request = get_object_or_404(
                BorrowRequest.objects.select_for_update(),
                pk=request_id,
            )

            if borrow_request.status != BorrowRequest.PENDING:
                messages.error(
                    request,
                    "Only pending requests can be approved.",
                )
                return redirect("request_review")

            request_items = list(
                RequestItem.objects
                .filter(request=borrow_request)
                .select_related("catalog_item")
                .order_by("catalog_item_id", "id")
            )

            if not request_items:
                messages.error(
                    request,
                    "This request has no equipment items to allocate.",
                )
                return redirect("request_review")

            max_quantity = SystemSetting.get_int("max_quantity", 3)

            for item in request_items:
                if item.quantity > max_quantity:
                    messages.error(
                        request,
                        (
                            f"Requested quantity for '{item.catalog_item.name}' "
                            f"exceeds the maximum of {max_quantity} units per item."
                        ),
                    )
                    return redirect("request_review")

            allocation_plan = []
            selected_unit_ids = set()
            seen_catalog_item_ids = set()
            active_allocated_unit_ids = set(
                UnitAllocation.objects.filter(
                    released_at__isnull=True,
                ).values_list("unit_id", flat=True)
            )

            for request_item in request_items:
                if request_item.quantity < 1:
                    messages.error(request, "A requested quantity is invalid.")
                    return redirect("request_review")

                if request_item.quantity > max_quantity:
                    messages.error(
                        request,
                        (
                            f"Requested quantity for '{request_item.catalog_item.name}' "
                            f"exceeds the maximum of {max_quantity} units per item."
                        ),
                    )
                    return redirect("request_review")

                if request_item.catalog_item_id in seen_catalog_item_ids:
                    messages.error(
                        request,
                        (
                            f"'{request_item.catalog_item.name}' appears more than once "
                            "in this request. Correct the duplicate item rows first."
                        ),
                    )
                    return redirect("request_review")

                seen_catalog_item_ids.add(request_item.catalog_item_id)

                if UnitAllocation.objects.filter(
                    request_item=request_item,
                    released_at__isnull=True,
                ).exists():
                    messages.error(
                        request,
                        (
                            "This request already has unit allocations. "
                            "Review its records before proceeding."
                        ),
                    )
                    return redirect("request_review")

                available_units = list(
                    EquipmentUnit.objects.select_for_update()
                    .filter(
                        catalog_item_id=request_item.catalog_item_id,
                        status=EquipmentUnit.AVAILABLE,
                    )
                    .exclude(pk__in=active_allocated_unit_ids)
                    .exclude(pk__in=selected_unit_ids)
                    .order_by("asset_code")[:request_item.quantity]
                )

                if len(available_units) < request_item.quantity:
                    messages.error(
                        request,
                        (
                            f"Insufficient available units for "
                            f"'{request_item.catalog_item.name}'. "
                            "No units were reserved."
                        ),
                    )
                    return redirect("request_review")

                selected_unit_ids.update(unit.pk for unit in available_units)
                allocation_plan.append((request_item, available_units))

            for request_item, units in allocation_plan:
                for unit in units:
                    updated_count = EquipmentUnit.objects.filter(
                        pk=unit.pk,
                        status=EquipmentUnit.AVAILABLE,
                    ).update(status=EquipmentUnit.RESERVED)

                    if updated_count != 1:
                        raise RuntimeError(
                            f"Unit {unit.asset_code} is no longer available."
                        )

                    UnitAllocation.objects.create(
                        request_item=request_item,
                        unit=unit,
                    )

            borrow_request.status = BorrowRequest.APPROVED
            borrow_request.admin_remarks = remarks
            borrow_request.save(
                update_fields=["status", "admin_remarks"]
            )

            AuditLog.objects.create(
                actor=request.user,
                action="REQUEST_APPROVED",
                details=(
                    f"Approved request #{borrow_request.pk} "
                    f"for borrower '{borrow_request.user.username}'. "
                    f"Reserved asset codes: "
                    f"{', '.join(
                        unit.asset_code
                        for _, units in allocation_plan
                        for unit in units
                    )}."
                ),
            )

    except Exception:
        raise

    messages.success(
        request,
        f"Request #{request_id} approved and equipment reserved.",
    )
    return redirect("request_review")

@admin_required
@require_POST
def request_reject(request, request_id):
    reason = request.POST.get("rejection_reason", "").strip()

    if not reason:
        messages.error(
            request,
            "A rejection reason is required.",
        )
        return redirect("request_review")

    with transaction.atomic():
        borrow_request = get_object_or_404(
            BorrowRequest.objects.select_for_update(),
            pk=request_id,
        )

        if borrow_request.status != BorrowRequest.PENDING:
            messages.error(
                request,
                "Only pending requests can be rejected.",
            )
            return redirect("request_review")

        borrow_request.status = BorrowRequest.REJECTED
        borrow_request.admin_remarks = reason
        borrow_request.save(
            update_fields=["status", "admin_remarks"]
        )

        AuditLog.objects.create(
            actor=request.user,
            action="REQUEST_REJECTED",
            details=(
                f"Rejected request #{borrow_request.pk} "
                f"for borrower '{borrow_request.user.username}'. "
                f"Reason: {reason}"
            ),
        )

    messages.success(
        request,
        f"Request #{request_id} rejected.",
    )
    return redirect("request_review")


# --- HELPER FUNCTIONS FROM admin_operations.py ---

def _max_loan_duration_days():
    setting = SystemSetting.objects.filter(
        key="max_loan_duration_days"
    ).first()
    if setting is None:
        setting = SystemSetting.objects.filter(key="max_loan_duration").first()
    if setting is None:
        return 7
    try:
        return max(1, int(setting.value))
    except (TypeError, ValueError):
        return 7


def _max_quantity():
    return SystemSetting.get_int("max_quantity", 3)


def _request_search(queryset, search_query):
    if search_query:
        queryset = queryset.filter(
            Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(purpose__icontains=search_query)
            | Q(items__catalog_item__name__icontains=search_query)
            | Q(items__catalog_item__category__name__icontains=search_query)
        ).distinct()
    return queryset


# --- VIEWS FROM admin_operations.py ---

@admin_required
def release_management(request):
    search_query = request.GET.get("q", "").strip()
    today = timezone.localdate()
    max_duration = _max_loan_duration_days()
    max_due_date = today + timedelta(days=max_duration)

    approved_queryset = BorrowRequest.objects.filter(
        status=BorrowRequest.APPROVED
    ).select_related("user").prefetch_related(
        "items__catalog_item",
        "items__allocations__unit",
    ).order_by("return_date", "requested_at", "id")
    approved_queryset = _request_search(approved_queryset, search_query)

    page_obj = Paginator(approved_queryset, 10).get_page(
        request.GET.get("page")
    )

    issued_loans = Loan.objects.select_related(
        "request",
        "request__user",
        "issued_by",
    ).prefetch_related(
        "request__items__catalog_item",
        "request__items__allocations__unit",
    ).order_by("-issued_at", "-id")

    if search_query:
        issued_loans = issued_loans.filter(
            Q(request__user__username__icontains=search_query)
            | Q(request__user__first_name__icontains=search_query)
            | Q(request__user__last_name__icontains=search_query)
            | Q(request__purpose__icontains=search_query)
            | Q(request__items__catalog_item__name__icontains=search_query)
            | Q(request__items__allocations__unit__asset_code__icontains=search_query)
        ).distinct()

    return render(
        request,
        "manage/release_management.html",
        {
            "page_obj": page_obj,
            "approved_requests": page_obj.object_list,
            "issued_loans": issued_loans[:25],
            "search_query": search_query,
            "today": today,
            "max_due_date": max_due_date,
            "max_loan_duration_days": max_duration,
        },
    )


@admin_required
@require_POST
def revise_approved_due_date(request, request_id):
    due_date = parse_date(request.POST.get("due_date", "").strip())
    reason = request.POST.get("reason", "").strip()
    today = timezone.localdate()
    max_duration = _max_loan_duration_days()

    if due_date is None or not reason:
        messages.error(request, "A valid revised due date and reason are required.")
        return redirect("release_management")

    if due_date < today or due_date > today + timedelta(days=max_duration):
        messages.error(
            request,
            f"The revised due date must be from today through the next {max_duration} calendar days.",
        )
        return redirect("release_management")

    with transaction.atomic():
        borrow_request = get_object_or_404(
            BorrowRequest.objects.select_for_update(),
            pk=request_id,
        )

        if borrow_request.status != BorrowRequest.APPROVED:
            messages.error(request, "Only approved requests can have their due date revised before issue.")
            return redirect("release_management")

        old_due_date = borrow_request.return_date
        existing_remarks = borrow_request.admin_remarks.strip()
        revision_note = (
            f"Due date revised before issue from {old_due_date.isoformat()} "
            f"to {due_date.isoformat()}. Reason: {reason}"
        )
        borrow_request.return_date = due_date
        borrow_request.admin_remarks = "\n".join(
            value for value in [existing_remarks, revision_note] if value
        )
        borrow_request.save(update_fields=["return_date", "admin_remarks"])

        AuditLog.objects.create(
            actor=request.user,
            action="DUE_DATE_REVISED_BEFORE_ISSUE",
            details=(
                f"Revised due date for request #{borrow_request.pk} from "
                f"{old_due_date.isoformat()} to {due_date.isoformat()}. "
                f"Reason: {reason}"
            ),
        )

    messages.success(request, f"Due date for request #{request_id} was revised.")
    return redirect("release_management")


@admin_required
@require_POST
def issue_approved_request(request, request_id):
    today = timezone.localdate()
    max_duration = _max_loan_duration_days()

    try:
        with transaction.atomic():
            borrow_request = get_object_or_404(
                BorrowRequest.objects.select_for_update().select_related("user"),
                pk=request_id,
            )

            if borrow_request.status != BorrowRequest.APPROVED:
                messages.error(request, "Only approved requests can be issued.")
                return redirect("release_management")

            if Loan.objects.filter(request=borrow_request).exists():
                messages.error(request, "This request already has an issued loan.")
                return redirect("release_management")

            if borrow_request.return_date < today:
                messages.error(
                    request,
                    "This request's due date has passed. Revise the due date with a recorded reason before issuing.",
                )
                return redirect("release_management")

            if borrow_request.return_date > today + timedelta(days=max_duration):
                messages.error(
                    request,
                    f"The due date exceeds the configured maximum loan duration of {max_duration} days.",
                )
                return redirect("release_management")

            request_items = list(
                RequestItem.objects.filter(request=borrow_request)
                .select_related("catalog_item")
                .order_by("id")
            )

            if not request_items:
                messages.error(request, "This request has no equipment items to issue.")
                return redirect("release_management")

            allocation_plan = []
            all_unit_ids = []

            for request_item in request_items:
                if request_item.quantity < 1:
                    messages.error(request, "A requested quantity is invalid.")
                    return redirect("release_management")

                allocated_ids = list(
                    UnitAllocation.objects.filter(
                        request_item=request_item,
                        released_at__isnull=True,
                    )
                    .order_by("unit_id")
                    .values_list("unit_id", flat=True)
                )

                if (
                    len(allocated_ids) != request_item.quantity
                    or len(set(allocated_ids)) != request_item.quantity
                ):
                    messages.error(
                        request,
                        f"Request #{borrow_request.pk} does not have enough valid allocations for {request_item.catalog_item.name}.",
                    )
                    return redirect("release_management")

                allocation_plan.append((request_item, allocated_ids))
                all_unit_ids.extend(allocated_ids)

            if len(set(all_unit_ids)) != len(all_unit_ids):
                messages.error(
                    request,
                    "The request contains duplicate physical-unit allocations and cannot be issued.",
                )
                return redirect("release_management")

            locked_units = list(
                EquipmentUnit.objects.select_for_update()
                .filter(pk__in=all_unit_ids)
                .select_related("catalog_item")
                .order_by("id")
            )
            unit_by_id = {unit.pk: unit for unit in locked_units}

            if len(unit_by_id) != len(all_unit_ids):
                messages.error(request, "One or more allocated units no longer exist.")
                return redirect("release_management")

            for request_item, allocated_ids in allocation_plan:
                for unit_id in allocated_ids:
                    unit = unit_by_id[unit_id]

                    if (
                        unit.status != EquipmentUnit.RESERVED
                        or unit.catalog_item_id != request_item.catalog_item_id
                    ):
                        messages.error(
                            request,
                            f"Asset {unit.asset_code} is not a valid reserved unit for this request.",
                        )
                        return redirect("release_management")

                    other_approved_allocation = UnitAllocation.objects.filter(
                        unit_id=unit_id,
                        released_at__isnull=True,
                        request_item__request__status=BorrowRequest.APPROVED,
                    ).exclude(request_item__request=borrow_request).exists()

                    if other_approved_allocation:
                        messages.error(
                            request,
                            f"Asset {unit.asset_code} is allocated to another approved request.",
                        )
                        return redirect("release_management")

            loan = Loan.objects.create(
                request=borrow_request,
                issued_by=request.user,
            )

            for unit in locked_units:
                unit.status = EquipmentUnit.ISSUED
                unit.save(update_fields=["status"])

            borrow_request.status = BorrowRequest.ISSUED
            borrow_request.save(update_fields=["status"])

            asset_codes = ", ".join(unit.asset_code for unit in locked_units)
            AuditLog.objects.create(
                actor=request.user,
                action="LOAN_ISSUED",
                details=(
                    f"Issued request #{borrow_request.pk} as loan #{loan.pk} "
                    f"to '{borrow_request.user.username}'. "
                    f"Release date: {loan.issued_at.isoformat()}. "
                    f"Due date: {borrow_request.return_date.isoformat()}. "
                    f"Asset codes: {asset_codes}."
                ),
            )
    except IntegrityError:
        messages.error(
            request,
            "The request could not be issued because a matching loan already exists. Refresh and review the request.",
        )
        return redirect("release_management")

    messages.success(request, f"Request #{request_id} has been issued.")
    return redirect("borrowing_slip", request_id=request_id)


@admin_required
def borrowing_slip(request, request_id):
    loan = get_object_or_404(
        Loan.objects.select_related(
            "request",
            "request__user",
            "issued_by",
        ).prefetch_related(
            "request__items__catalog_item",
            "request__items__allocations__unit",
        ),
        request_id=request_id,
    )

    return render(
        request,
        "manage/borrowing_slip.html",
        {
            "loan": loan,
            "borrow_request": loan.request,
        },
    )


@admin_required
def return_management(request):
    search_query = request.GET.get("q", "").strip()
    today = timezone.localdate()

    loans_queryset = Loan.objects.filter(
        request__status__in=[
            BorrowRequest.ISSUED,
            BorrowRequest.PARTIALLY_RETURNED,
        ]
    ).select_related(
        "request",
        "request__user",
        "issued_by",
    ).prefetch_related(
        "request__items__catalog_item",
        "request__items__allocations__unit",
        "returns__unit",
    ).order_by("request__return_date", "-issued_at")

    if search_query:
        loans_queryset = loans_queryset.filter(
            Q(request__user__username__icontains=search_query)
            | Q(request__user__first_name__icontains=search_query)
            | Q(request__user__last_name__icontains=search_query)
            | Q(request__purpose__icontains=search_query)
            | Q(request__items__catalog_item__name__icontains=search_query)
            | Q(request__items__allocations__unit__asset_code__icontains=search_query)
        ).distinct()

    loan_rows = []

    for loan in loans_queryset:
        allocated_units = {}
        for request_item in loan.request.items.all():
            for allocation in request_item.allocations.all():
                allocated_units.setdefault(allocation.unit_id, allocation.unit)

        returned_by_unit = {}
        for return_record in loan.returns.all():
            returned_by_unit.setdefault(return_record.unit_id, return_record)

        unit_rows = []
        for unit in sorted(allocated_units.values(), key=lambda item: item.asset_code):
            return_record = returned_by_unit.get(unit.pk)
            unit_rows.append(
                {
                    "unit": unit,
                    "return_record": return_record,
                    "can_return": return_record is None and unit.status == EquipmentUnit.ISSUED,
                }
            )

        outstanding_count = sum(
            1 for row in unit_rows if row["return_record"] is None
        )
        due_date = loan.request.return_date
        overdue_days = (
            (today - due_date).days
            if outstanding_count and due_date < today
            else 0
        )

        loan_rows.append(
            {
                "loan": loan,
                "due_date": due_date,
                "units": unit_rows,
                "outstanding_count": outstanding_count,
                "overdue_days": overdue_days,
                "is_overdue": overdue_days > 0,
            }
        )

    page_obj = Paginator(loan_rows, 10).get_page(request.GET.get("page"))

    return render(
        request,
        "manage/return_management.html",
        {
            "page_obj": page_obj,
            "loan_rows": page_obj.object_list,
            "search_query": search_query,
            "today": today,
        },
    )


@admin_required
@require_POST
def record_unit_return(request, loan_id, unit_id):
    condition_status = request.POST.get("condition_status", "").strip()
    condition_notes = request.POST.get("condition_notes", "").strip()
    allowed_conditions = {"Good", "Damaged", "Needs Repair", "Other"}

    if condition_status not in allowed_conditions:
        messages.error(request, "Choose a valid condition for the returned unit.")
        return redirect("return_management")

    condition_text = condition_status
    if condition_notes:
        condition_text = f"{condition_status}: {condition_notes}"

    damaged = condition_status in {"Damaged", "Needs Repair"}

    with transaction.atomic():
        loan = get_object_or_404(
            Loan.objects.select_for_update().select_related("request"),
            pk=loan_id,
        )

        if loan.request.status not in [
            BorrowRequest.ISSUED,
            BorrowRequest.PARTIALLY_RETURNED,
        ]:
            messages.error(request, "Returns can only be recorded for active loans.")
            return redirect("return_management")

        unit = get_object_or_404(
            EquipmentUnit.objects.select_for_update(),
            pk=unit_id,
        )

        allocated_to_loan = UnitAllocation.objects.filter(
            request_item__request=loan.request,
            unit=unit,
            released_at__isnull=True,
        ).exists()

        if not allocated_to_loan:
            messages.error(request, "This unit is not allocated to the selected loan.")
            return redirect("return_management")

        if ReturnRecord.objects.filter(loan=loan, unit=unit).exists():
            messages.error(request, f"Asset {unit.asset_code} has already been returned for this loan.")
            return redirect("return_management")

        if unit.status != EquipmentUnit.ISSUED:
            messages.error(
                request,
                f"Asset {unit.asset_code} is not currently marked as issued and cannot be returned.",
            )
            return redirect("return_management")

        return_record = ReturnRecord.objects.create(
            loan=loan,
            unit=unit,
            condition_on_return=condition_text,
            received_by=request.user,
        )

        unit.condition = condition_text
        if damaged:
            unit.status = EquipmentUnit.MAINTENANCE
        else:
            unit.status = EquipmentUnit.AVAILABLE
        unit.save(update_fields=["condition", "status"])

        if damaged:
            MaintenanceRecord.objects.create(
                unit=unit,
                problem_description=f"Returned in {condition_status.lower()} condition. {condition_notes}".strip(),
                handled_by=request.user,
            )

        UnitAllocation.objects.filter(
            request_item__request=loan.request,
            unit=unit,
            released_at__isnull=True,
        ).update(
            released_at=timezone.now(),
            release_reason=UnitAllocation.RETURNED,
        )

        allocated_ids = set(
            UnitAllocation.objects.filter(
                request_item__request=loan.request
            ).values_list("unit_id", flat=True)
        )
        returned_ids = set(
            ReturnRecord.objects.filter(loan=loan).values_list("unit_id", flat=True)
        )

        if allocated_ids and allocated_ids.issubset(returned_ids):
            loan.request.status = BorrowRequest.RETURNED
        else:
            loan.request.status = BorrowRequest.PARTIALLY_RETURNED
        loan.request.save(update_fields=["status"])

        AuditLog.objects.create(
            actor=request.user,
            action="EQUIPMENT_UNIT_RETURNED",
            details=(
                f"Recorded return of asset {unit.asset_code} for loan #{loan.pk} "
                f"on {return_record.returned_at.isoformat()}. "
                f"Condition: {condition_text}. "
                f"Resulting unit status: {unit.status}."
            ),
        )

        if damaged:
            AuditLog.objects.create(
                actor=request.user,
                action="DAMAGED_UNIT_SENT_TO_MAINTENANCE",
                details=(
                    f"Asset {unit.asset_code} from loan #{loan.pk} was sent to maintenance. "
                    f"Problem: {condition_text}."
                ),
            )

    if damaged:
        messages.warning(
            request,
            f"Asset {unit.asset_code} was returned and routed to maintenance.",
        )
    else:
        messages.success(request, f"Asset {unit.asset_code} was returned successfully.")

    return redirect("return_management")


@admin_required
def maintenance_management(request):
    search_query = request.GET.get("q", "").strip()

    open_records = MaintenanceRecord.objects.filter(
        fixed_at__isnull=True
    ).select_related(
        "unit",
        "unit__catalog_item",
        "unit__catalog_item__category",
        "handled_by",
    ).order_by("-reported_at", "-id")

    closed_records = MaintenanceRecord.objects.filter(
        fixed_at__isnull=False
    ).select_related(
        "unit",
        "unit__catalog_item",
        "unit__catalog_item__category",
        "handled_by",
    ).order_by("-fixed_at", "-id")

    if search_query:
        record_filter = (
            Q(unit__asset_code__icontains=search_query)
            | Q(unit__catalog_item__name__icontains=search_query)
            | Q(unit__catalog_item__category__name__icontains=search_query)
            | Q(problem_description__icontains=search_query)
            | Q(action_taken__icontains=search_query)
            | Q(handled_by__username__icontains=search_query)
        )
        open_records = open_records.filter(record_filter)
        closed_records = closed_records.filter(record_filter)

    active_record_unit_ids = MaintenanceRecord.objects.filter(
        fixed_at__isnull=True
    ).values_list("unit_id", flat=True)

    maintenance_candidates = EquipmentUnit.objects.filter(
        status=EquipmentUnit.AVAILABLE
    ).exclude(
        pk__in=active_record_unit_ids
    ).select_related(
        "catalog_item",
        "catalog_item__category",
    ).order_by("catalog_item__name", "asset_code")

    inventory_counts = []
    for status_value, status_label in EquipmentUnit.STATUS_CHOICES:
        inventory_counts.append(
            {
                "status": status_value,
                "label": status_label,
                "count": EquipmentUnit.objects.filter(status=status_value).count(),
            }
        )

    inventory_total = EquipmentUnit.objects.count()
    classified_total = sum(row["count"] for row in inventory_counts)
    unclassified_total = inventory_total - classified_total

    return render(
        request,
        "manage/maintenance_management.html",
        {
            "open_records": open_records,
            "closed_records": closed_records[:50],
            "maintenance_candidates": maintenance_candidates,
            "inventory_counts": inventory_counts,
            "inventory_total": inventory_total,
            "classified_total": classified_total,
            "unclassified_total": unclassified_total,
            "search_query": search_query,
        },
    )


@admin_required
def audit_settings_management(request):
    if request.method == "POST":
        max_duration_text = request.POST.get("max_loan_duration_days", "").strip()
        max_quantity_text = request.POST.get("max_quantity", "").strip()
        try:
            max_duration = int(max_duration_text)
            max_quantity = int(max_quantity_text)
        except (TypeError, ValueError):
            messages.error(request, "Enter whole-number values for both settings.")
            return redirect("audit_settings_management")

        if not 1 <= max_duration <= 3650 or not 1 <= max_quantity <= 1000:
            messages.error(
                request,
                "Maximum loan duration must be 1–3650 days and maximum quantity must be 1–1000 units.",
            )
            return redirect("audit_settings_management")

        old_duration = _max_loan_duration_days()
        old_quantity = _max_quantity()
        with transaction.atomic():
            SystemSetting.objects.update_or_create(
                key="max_loan_duration_days",
                defaults={
                    "value": str(max_duration),
                    "description": "Maximum permitted loan duration in calendar days.",
                },
            )
            SystemSetting.objects.update_or_create(
                key="max_quantity",
                defaults={
                    "value": str(max_quantity),
                    "description": "Maximum number of physical units in one request.",
                },
            )
            AuditLog.objects.create(
                actor=request.user,
                action="SYSTEM_SETTINGS_UPDATED",
                details=(
                    f"Updated maximum loan duration from {old_duration} to {max_duration} days "
                    f"and maximum request quantity from {old_quantity} to {max_quantity} units."
                ),
            )
        messages.success(request, "System settings updated.")
        return redirect("audit_settings_management")

    search_query = request.GET.get("q", "").strip()
    date_from_text = request.GET.get("date_from", "").strip()
    date_to_text = request.GET.get("date_to", "").strip()
    date_from = parse_date(date_from_text) if date_from_text else None
    date_to = parse_date(date_to_text) if date_to_text else None

    logs = AuditLog.objects.select_related("actor").order_by("-timestamp", "-id")
    if search_query:
        logs = logs.filter(
            Q(action__icontains=search_query)
            | Q(details__icontains=search_query)
            | Q(actor__username__icontains=search_query)
        )

    filters_valid = (
        (not date_from_text or date_from is not None)
        and (not date_to_text or date_to is not None)
        and not (date_from and date_to and date_from > date_to)
    )
    if not filters_valid:
        messages.error(request, "Enter a valid audit date range.")
        date_from = None
        date_to = None
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    page_obj = Paginator(logs, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "manage/audit_settings.html",
        {
            "page_obj": page_obj,
            "logs": page_obj.object_list,
            "search_query": search_query,
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
            "max_loan_duration_days": _max_loan_duration_days(),
            "max_quantity": _max_quantity(),
        },
    )


@admin_required
@require_POST
def open_maintenance_record(request):
    unit_id = request.POST.get("unit_id", "").strip()
    problem_description = request.POST.get("problem_description", "").strip()

    if not unit_id or not problem_description:
        messages.error(request, "Select an equipment unit and describe the problem.")
        return redirect("maintenance_management")

    with transaction.atomic():
        unit = get_object_or_404(
            EquipmentUnit.objects.select_for_update(),
            pk=unit_id,
        )

        if unit.status in [EquipmentUnit.ISSUED, EquipmentUnit.RESERVED]:
            messages.error(
                request,
                "Maintenance cannot be opened for an issued or reserved unit.",
            )
            return redirect("maintenance_management")

        if unit.status == EquipmentUnit.RETIRED:
            messages.error(request, "Retired units remain unavailable and cannot be placed into maintenance.")
            return redirect("maintenance_management")

        active_record_exists = MaintenanceRecord.objects.filter(
            unit=unit,
            fixed_at__isnull=True,
        ).exists()

        if active_record_exists:
            messages.error(request, f"Asset {unit.asset_code} already has an open maintenance record.")
            return redirect("maintenance_management")

        if unit.status not in [EquipmentUnit.AVAILABLE, EquipmentUnit.MAINTENANCE]:
            messages.error(request, "This unit cannot be placed into maintenance from its current status.")
            return redirect("maintenance_management")

        maintenance_record = MaintenanceRecord.objects.create(
            unit=unit,
            problem_description=problem_description,
            handled_by=request.user,
        )

        unit.status = EquipmentUnit.MAINTENANCE
        unit.save(update_fields=["status"])

        AuditLog.objects.create(
            actor=request.user,
            action="MAINTENANCE_OPENED",
            details=(
                f"Opened maintenance record #{maintenance_record.pk} for asset "
                f"{unit.asset_code}. Problem: {problem_description}"
            ),
        )

    messages.success(request, f"Maintenance was opened for asset {unit.asset_code}.")
    return redirect("maintenance_management")


@admin_required
@require_POST
def close_maintenance_record(request, record_id):
    action_taken = request.POST.get("action_taken", "").strip()

    if not action_taken:
        messages.error(request, "Describe the repair or action taken before closing maintenance.")
        return redirect("maintenance_management")

    with transaction.atomic():
        maintenance_record = get_object_or_404(
            MaintenanceRecord.objects.select_for_update().select_related("unit"),
            pk=record_id,
        )

        if maintenance_record.fixed_at is not None:
            messages.error(request, "This maintenance record is already closed.")
            return redirect("maintenance_management")

        unit = get_object_or_404(
            EquipmentUnit.objects.select_for_update(),
            pk=maintenance_record.unit_id,
        )

        if unit.status in [EquipmentUnit.ISSUED, EquipmentUnit.RESERVED]:
            messages.error(
                request,
                "Maintenance cannot be closed while the unit is issued or reserved.",
            )
            return redirect("maintenance_management")

        maintenance_record.action_taken = action_taken
        maintenance_record.fixed_at = timezone.now()
        maintenance_record.handled_by = request.user
        maintenance_record.save(
            update_fields=["action_taken", "fixed_at", "handled_by"]
        )

        if unit.status != EquipmentUnit.RETIRED:
            unit.status = EquipmentUnit.AVAILABLE
            unit.save(update_fields=["status"])

        AuditLog.objects.create(
            actor=request.user,
            action="MAINTENANCE_CLOSED",
            details=(
                f"Closed maintenance record #{maintenance_record.pk} for asset "
                f"{unit.asset_code}. Action taken: {action_taken}. "
                f"Resulting unit status: {unit.status}."
            ),
        )

    messages.success(request, f"Maintenance record #{record_id} was closed.")
    return redirect("maintenance_management")

@login_required
def profile_view(request):

    if not request.user.profile.is_active:
        return redirect('logout')

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user.profile, user=request.user)
        if form.is_valid():
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.save()
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile_view')
    else:
        form = UserProfileForm(instance=request.user.profile, user=request.user)

    return render(request, 'portal/profile.html', {'form': form})

@login_required
def portal_home(request):
    """Landing page for the basic-user area, with a safe admin redirect."""
    profile = getattr(request.user, "profile", None)
    if (
        profile is not None
        and profile.is_active
        and profile.role == UserProfile.ADMIN
    ):
        return redirect("admin_dashboard")

    return browse_catalog(request)


@basic_user_required
def browse_catalog(request):
    search_query = request.GET.get("q", "").strip()
    items = _portal_catalog_items()

    if search_query:
        items = items.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(category__name__icontains=search_query)
        )

    return render(
        request,
        "portal/catalog.html",
        {
            "items": items,
            "search_query": search_query,
        },
    )


def _portal_catalog_items():
    return CatalogItem.objects.filter(
        is_archived=False,
        category__is_archived=False,
    ).annotate(
        available_quantity=Count(
            "units",
            filter=Q(units__status=EquipmentUnit.AVAILABLE),
        ),
        serviceable_quantity=Count(
            "units",
            filter=~Q(
                units__status__in=[
                    EquipmentUnit.RETIRED,
                    EquipmentUnit.MAINTENANCE,
                ]
            ),
        ),
    ).select_related("category").order_by("category__name", "name")


@basic_user_required
def borrow_request_create(request):
    catalog_items = _portal_catalog_items()
    max_quantity = SystemSetting.get_int("max_quantity", 3)
    max_duration = _max_loan_duration_days()
    form_kwargs = {
        "catalog_items": catalog_items,
        "max_quantity": max_quantity,
        "max_loan_duration_days": max_duration,
    }

    if request.method == "POST":
        form = BorrowRequestForm(request.POST, **form_kwargs)
        if form.is_valid():
            with transaction.atomic():
                borrow_request = BorrowRequest.objects.create(
                    user=request.user,
                    purpose=form.cleaned_data["purpose"],
                    return_date=form.cleaned_data["return_date"],
                    status=BorrowRequest.PENDING,
                )
                RequestItem.objects.bulk_create(
                    [
                        RequestItem(
                            request=borrow_request,
                            catalog_item=item,
                            quantity=quantity,
                        )
                        for item, quantity in form.cleaned_data["requested_items"]
                    ]
                )
                AuditLog.objects.create(
                    actor=request.user,
                    action="REQUEST_SUBMITTED",
                    details=(
                        f"Submitted request #{borrow_request.pk} for "
                        f"{', '.join(
                            f'{quantity}x {item.name}'
                            for item, quantity in form.cleaned_data['requested_items']
                        )}. Requested return date: "
                        f"{borrow_request.return_date.isoformat()}."
                    ),
                )

            messages.success(
                request,
                f"Request #{borrow_request.pk} submitted and is pending review.",
            )
            return redirect("request_history")
    else:
        initial = {}
        initial_item_id = request.GET.get("item", "").strip()
        if initial_item_id.isdigit() and catalog_items.filter(
            pk=initial_item_id
        ).exists():
            initial["item_1"] = initial_item_id
            initial["quantity_1"] = 1

        form = BorrowRequestForm(**form_kwargs, initial=initial)

    today = timezone.localdate()
    form.fields["return_date"].widget.attrs.update(
        {
            "min": (today + timedelta(days=1)).isoformat(),
            "max": (today + timedelta(days=max_duration)).isoformat(),
        }
    )

    return render(
        request,
        "portal/request_form.html",
        {
            "form": form,
            "item_rows": [
                (form[f"item_{position}"], form[f"quantity_{position}"])
                for position in range(1, 4)
            ],
            "max_quantity": max_quantity,
            "max_loan_duration_days": max_duration,
            "today": today,
            "max_return_date": today + timedelta(days=max_duration),
        },
    )


@basic_user_required
def request_history(request):
    requests = (
        BorrowRequest.objects.filter(user=request.user)
        .prefetch_related(
            "items__catalog_item__category",
            "items__allocations__unit",
            "loan__returns__unit",
        )
        .order_by("-requested_at", "-id")
    )
    page_obj = Paginator(requests, 10).get_page(request.GET.get("page"))
    history_rows = []
    today = timezone.localdate()

    for borrow_request in page_obj.object_list:
        try:
            loan = borrow_request.loan
        except Loan.DoesNotExist:
            loan = None

        returns_by_unit_id = (
            {return_record.unit_id: return_record for return_record in loan.returns.all()}
            if loan
            else {}
        )
        item_rows = []
        for request_item in borrow_request.items.all():
            allocations = [
                (
                    allocation,
                    returns_by_unit_id.get(allocation.unit_id),
                )
                for allocation in request_item.allocations.all()
            ]
            item_rows.append(
                {
                    "request_item": request_item,
                    "allocations": allocations,
                }
            )

        history_rows.append(
            {
                "borrow_request": borrow_request,
                "loan": loan,
                "item_rows": item_rows,
                "is_overdue": (
                    loan is not None
                    and borrow_request.status
                    in (
                        BorrowRequest.ISSUED,
                        BorrowRequest.PARTIALLY_RETURNED,
                    )
                    and borrow_request.return_date < today
                ),
            }
        )

    return render(
        request,
        "portal/request_history.html",
        {
            "page_obj": page_obj,
            "history_rows": history_rows,
        },
    )


@basic_user_required
@require_POST
def cancel_borrow_request(request, request_id):
    with transaction.atomic():
        borrow_request = get_object_or_404(
            BorrowRequest.objects.select_for_update(),
            pk=request_id,
            user=request.user,
        )

        if borrow_request.status not in (
            BorrowRequest.PENDING,
            BorrowRequest.APPROVED,
        ):
            messages.error(
                request,
                "Only pending or approved requests can be cancelled.",
            )
            return redirect("request_history")

        allocation_ids = list(
            UnitAllocation.objects.filter(
                request_item__request=borrow_request,
                released_at__isnull=True,
            ).values_list("unit_id", flat=True)
        )
        units = list(
            EquipmentUnit.objects.select_for_update()
            .filter(pk__in=allocation_ids)
            .order_by("id")
        )

        if len(units) != len(allocation_ids) or any(
            unit.status != EquipmentUnit.RESERVED for unit in units
        ):
            messages.error(
                request,
                "The reserved equipment could not be released. Contact an administrator.",
            )
            return redirect("request_history")

        released_asset_codes = [unit.asset_code for unit in units]
        for unit in units:
            unit.status = EquipmentUnit.AVAILABLE
            unit.save(update_fields=["status"])

        if allocation_ids:
            UnitAllocation.objects.filter(
                request_item__request=borrow_request,
                released_at__isnull=True,
            ).update(
                released_at=timezone.now(),
                release_reason=UnitAllocation.CANCELLED,
            )

        borrow_request.status = BorrowRequest.CANCELLED
        borrow_request.save(update_fields=["status"])
        AuditLog.objects.create(
            actor=request.user,
            action="REQUEST_CANCELLED",
            details=(
                f"Cancelled request #{borrow_request.pk}. Released asset codes: "
                f"{', '.join(released_asset_codes) or 'none'}."
            ),
        )

    messages.success(request, f"Request #{request_id} cancelled.")
    return redirect("request_history")