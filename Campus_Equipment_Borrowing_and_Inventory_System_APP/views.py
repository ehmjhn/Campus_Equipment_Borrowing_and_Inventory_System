from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.utils import timezone
from .models import UserProfile, EquipmentUnit, BorrowRequest, Loan
from functools import wraps

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return login_required(view_func)(request, *args, **kwargs)

        try:
            if request.user.profile.role == UserProfile.ADMIN:
                return view_func(request, *args, **kwargs)
        except UserProfile.DoesNotExist:
            pass

        return HttpResponseForbidden("You do not have permission to access this page.")
    return _wrapped_view

@admin_required
def admin_dashboard(request):
    # Live metrics
    available_units_count = EquipmentUnit.objects.filter(status=EquipmentUnit.AVAILABLE).count()
    pending_requests_count = BorrowRequest.objects.filter(status=BorrowRequest.PENDING).count()

    # Active loans are loans whose associated request is in 'Issued' or 'Partially Returned' state
    active_loans_count = Loan.objects.filter(
        request__status__in=[BorrowRequest.ISSUED, BorrowRequest.PARTIALLY_RETURNED]
    ).count()

    # Overdue loans: Active loans where the return_date is less than today
    overdue_loans_count = Loan.objects.filter(
        request__status__in=[BorrowRequest.ISSUED, BorrowRequest.PARTIALLY_RETURNED],
        request__return_date__lt=timezone.now().date()
    ).count()

    context = {
        'available_units': available_units_count,
        'pending_requests': pending_requests_count,
        'active_loans': active_loans_count,
        'overdue_loans': overdue_loans_count,
    }

    return render(request, 'admin/dashboard.html', context)
