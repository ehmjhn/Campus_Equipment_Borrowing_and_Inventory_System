import csv
from functools import wraps

from django.contrib.auth import get_user_model
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
)

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
        status=EquipmentUnit.AVAILABLE
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

    loans = Loan.objects.select_related("request", "request__user", "issued_by")
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

    # Ensure every listed account has a profile.
    # Existing accounts are preserved; missing profiles default to BASIC_USER.
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
@require_POST
def toggle_account_status(request, user_id):
    with transaction.atomic():
        account = get_object_or_404(
            User.objects.select_for_update(),
            pk=user_id,
        )

        profile, _ = UserProfile.objects.get_or_create(user=account)

        # Prevent an administrator from deactivating their own account.
        if account.pk == request.user.pk:
            return redirect("account_management")

        currently_active = account.is_active and profile.is_active

        if currently_active:
            # Do not allow the last active admin to be deactivated.
            if profile.role == UserProfile.ADMIN:
                active_admin_count = UserProfile.objects.filter(
                    role=UserProfile.ADMIN,
                    is_active=True,
                    user__is_active=True,
                ).exclude(user_id=account.pk).count()

                if active_admin_count == 0:
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

    # Prevent archiving a category while it has active catalog items.
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

    # Archive the category and record the action together.
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

@admin_required
def physical_units_management(request):
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

    context = {
        "active_catalog_items": active_catalog_items,
        "equipment_units": equipment_units,
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

    # Do not archive an item while its units are reserved or issued.
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

    # Validate required fields.
    if not catalog_item_id or not asset_code or not condition or not acquisition_date_text:
        messages.error(
            request,
            "All equipment unit fields are required.",
        )
        return redirect("catalog_item_management")

    # Only active catalog items can receive new physical units.
    catalog_item = get_object_or_404(
        CatalogItem,
        pk=catalog_item_id,
        is_archived=False,
        category__is_archived=False,
    )

    # Validate the date supplied by the form.
    acquisition_date = parse_date(acquisition_date_text)

    if acquisition_date is None:
        messages.error(
            request,
            "Please provide a valid acquisition date.",
        )
        return redirect("catalog_item_management")

    # Check for an existing asset code.
    if EquipmentUnit.objects.filter(
        asset_code__iexact=asset_code
    ).exists():
        messages.error(
            request,
            "That asset code is already registered. Use a unique asset code.",
        )
        return redirect("catalog_item_management")

    # Save the unit and audit log together.
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
def request_review(request):
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()

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

    paginator = Paginator(requests, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "requests": page_obj.object_list,
        "search_query": search_query,
        "status_filter": status_filter,
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

            max_quantity = SystemSetting.get_int("max_quantity", 5)
            requested_quantity = sum(item.quantity for item in request_items)
            if requested_quantity > max_quantity:
                messages.error(
                    request,
                    f"This request contains {requested_quantity} units, above the configured maximum of {max_quantity}.",
                )
                return redirect("request_review")

            # Validate every requested quantity before changing any unit.
            allocation_plan = []

            for request_item in request_items:
                if request_item.quantity < 1:
                    messages.error(
                        request,
                        "A requested quantity is invalid.",
                    )
                    return redirect("request_review")

                already_allocated = UnitAllocation.objects.filter(
                    request_item=request_item
                ).exists()

                if already_allocated:
                    messages.error(
                        request,
                        "This request already has unit allocations. "
                        "Please review its records before proceeding.",
                    )
                    return redirect("request_review")

                available_units = list(
                    EquipmentUnit.objects
                    .select_for_update()
                    .filter(
                        catalog_item=request_item.catalog_item,
                        status=EquipmentUnit.AVAILABLE,
                    )
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

                allocation_plan.append(
                    (request_item, available_units)
                )

            # All requested items are available; reserve them together.
            for request_item, units in allocation_plan:
                for unit in units:
                    UnitAllocation.objects.create(
                        request_item=request_item,
                        unit=unit,
                    )

                    unit.status = EquipmentUnit.RESERVED
                    unit.save(update_fields=["status"])

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
        # Unexpected database errors should not leave partial allocations.
        # The transaction rolls back; let Django handle unexpected errors.
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