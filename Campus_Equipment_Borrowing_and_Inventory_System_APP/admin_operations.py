from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .models import (
    AuditLog,
    BorrowRequest,
    EquipmentUnit,
    Loan,
    MaintenanceRecord,
    RequestItem,
    ReturnRecord,
    SystemSetting,
    UnitAllocation,
)
from .views import admin_required


def _max_loan_duration_days():
    setting = SystemSetting.objects.filter(
        key__in=["max_loan_duration_days", "max_loan_duration"]
    ).order_by("key").first()
    if setting is None:
        return 7
    try:
        return max(1, int(setting.value))
    except (TypeError, ValueError):
        return 7


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
                    UnitAllocation.objects.filter(request_item=request_item)
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
