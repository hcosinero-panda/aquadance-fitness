from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import models
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from datetime import timedelta
from .models import Member, MembershipPlan, Payment, Attendance


# OWNER-ONLY DECORATOR
def owner_required(view_func):
    """Decorator: Only allow the owner (superuser/staff) to access"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "Access denied. Owner only.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('username'), password=request.POST.get('password'))
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, "Invalid credentials.")
    return render(request, 'core/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def dashboard_view(request):
    today = timezone.localtime(timezone.now()).date()
    
    # 1. HANDLE POST ACTIONS
    if request.method == 'POST' and 'process_membership_action' in request.POST:
        try:
            member = Member.objects.get(id=request.POST.get('member_id'))
            action = request.POST.get('action_type')
            
            if action == 'check_in':
                if Attendance.objects.filter(member=member, check_in_time__date=today).exists():
                    messages.warning(request, f"{member.first_name} has already checked in today.")
                else:
                    Attendance.objects.create(member=member)
                    messages.success(request, f"Attendance logged for {member.first_name}.")
            
            elif action == 'renew_plan':
                plan = MembershipPlan.objects.get(id=request.POST.get('plan_id'))
                expiration = today + timedelta(days=plan.duration_days)
                Payment.objects.create(
                    member=member, membership_plan=plan, 
                    amount_paid=plan.price, payment_date=today, 
                    expiration_date=expiration
                )
                messages.success(request, f"Plan renewed! Expires: {expiration.strftime('%b %d, %Y')}")
        
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
        return redirect('dashboard')

    # 2. AGGREGATE DATA
    search = request.GET.get('search', '').strip()
    members = Member.objects.all()
    
    if search:
        members = members.filter(models.Q(first_name__icontains=search) | models.Q(last_name__icontains=search))

    # 3. ENRICH MEMBER DATA WITH STATUS
    for m in members:
        latest_payment = Payment.objects.filter(member=m).order_by('-expiration_date').first()
        if latest_payment and latest_payment.expiration_date >= today:
            m.status = "Active"
            m.status_color = "text-emerald-400"
            m.bg_color = "bg-emerald-950/30"
        else:
            m.status = "Expired"
            m.status_color = "text-red-400"
            m.bg_color = "bg-red-950/30"

    context = {
        'members': members,
        'plans': MembershipPlan.objects.all().order_by('price'),
        'total_members': Member.objects.count(),
        'active_payments': Payment.objects.filter(expiration_date__gte=today).values('member').distinct().count(),
        'total_refills': Attendance.objects.filter(check_in_time__date=today).count(),
        'today_log': Attendance.objects.filter(check_in_time__date=today).order_by('-check_in_time'),
        'search_query': search,
    }
    return render(request, 'core/dashboard.html', context)


@login_required(login_url='login')
def expiration_alerts_view(request):
    """View for members expiring soon or already expired"""
    today = timezone.localtime(timezone.now()).date()
    seven_days_from_now = today + timedelta(days=7)
    
    # Get members expiring within 7 days
    expiring_soon = Member.objects.filter(
        payments__expiration_date__gte=today,
        payments__expiration_date__lte=seven_days_from_now
    ).distinct().order_by('payments__expiration_date')
    
    # Get expired members
    expired = Member.objects.filter(
        payments__expiration_date__lt=today
    ).exclude(
        payments__expiration_date__gte=today
    ).distinct().order_by('-payments__expiration_date')
    
    # Enrich with expiration data
    for member in expiring_soon:
        member.days_left = member.get_days_until_expiration()
        member.expiration = member.get_expiration_date()
    
    for member in expired:
        member.days_left = member.get_days_until_expiration()
        member.expiration = member.get_expiration_date()
    
    context = {
        'expiring_soon': expiring_soon,
        'expired': expired,
        'today': today,
        'expiring_count': expiring_soon.count(),
        'expired_count': expired.count(),
    }
    return render(request, 'core/expiration_alerts.html', context)


@login_required(login_url='login')
def checkin_page_view(request):
    """Kiosk-style QR code check-in page"""
    today = timezone.localtime(timezone.now()).date()
    recent_checkins = Attendance.objects.filter(check_in_time__date=today).order_by('-check_in_time')[:10]
    return render(request, 'core/checkin.html', {'recent_checkins': recent_checkins})


@login_required(login_url='login')
def membership_cards_view(request):
    """Printable membership cards with QR codes"""
    members = Member.objects.all().order_by('last_name', 'first_name')
    
    # Add QR code base64 to each member
    for member in members:
        member.qr_code_b64 = member.get_qr_code_base64()
        
        # Get member status
        today = timezone.localtime(timezone.now()).date()
        latest_payment = Payment.objects.filter(member=member).order_by('-expiration_date').first()
        if latest_payment and latest_payment.expiration_date >= today:
            member.is_active = True
        else:
            member.is_active = False
    
    return render(request, 'core/membership_cards.html', {'members': members})


@require_http_methods(["POST"])
def scan_qr_api(request):
    """API endpoint for QR code scanning or manual ID entry"""
    try:
        member_id = request.POST.get('member_id', '').strip().upper()
        
        if not member_id:
            return JsonResponse({'success': False, 'message': 'No member ID entered'}, status=400)
        
        member = Member.objects.get(member_id=member_id)
        today = timezone.localtime(timezone.now()).date()
        
        # Check membership status
        if not member.is_active():
            expiration = member.get_expiration_date()
            return JsonResponse({
                'success': False,
                'message': f'Membership expired on {expiration.strftime("%B %d, %Y")}' if expiration else 'No active membership',
                'member_name': f'{member.first_name} {member.last_name}',
                'member_id': member.member_id,
                'status': 'expired',
                'photo': member.photo.url if member.photo else None,
                'expiration_date': expiration.strftime('%B %d, %Y') if expiration else None
            })
        
        # Check if already checked in today
        if Attendance.objects.filter(member=member, check_in_time__date=today).exists():
            expiration = member.get_expiration_date()
            days_left = member.get_days_until_expiration()
            return JsonResponse({
                'success': False, 
                'message': f'{member.first_name} already checked in today!',
                'member_name': f'{member.first_name} {member.last_name}',
                'member_id': member.member_id,
                'status': 'duplicate',
                'photo': member.photo.url if member.photo else None,
                'expiration_date': expiration.strftime('%B %d, %Y') if expiration else None,
                'days_until_expiration': days_left
            })
        
        # Create attendance record
        attendance = Attendance.objects.create(member=member)
        local_time = timezone.localtime(attendance.check_in_time)
        expiration = member.get_expiration_date()
        days_left = member.get_days_until_expiration()
        
        return JsonResponse({
            'success': True,
            'message': f'Welcome {member.first_name}!',
            'member_name': f'{member.first_name} {member.last_name}',
            'member_id': member.member_id,
            'check_in_time': local_time.strftime('%I:%M %p'),
            'status': 'success',
            'photo': member.photo.url if member.photo else None,
            'expiration_date': expiration.strftime('%B %d, %Y') if expiration else None,
            'days_until_expiration': days_left
        })
    
    except Member.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Member not found', 'status': 'not_found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}', 'status': 'error'}, status=500)


# ============================================================================
# CUSTOM OWNER-ONLY ADMIN DASHBOARD (NOT Django Admin)
# ============================================================================

@owner_required
def admin_dashboard(request):
    """Main admin dashboard - owner only"""
    today = timezone.localtime(timezone.now()).date()
    
    context = {
        'total_members': Member.objects.count(),
        'active_members': Payment.objects.filter(expiration_date__gte=today).values('member').distinct().count(),
        'expired_members': Member.objects.exclude(
            payments__expiration_date__gte=today
        ).distinct().count(),
        'total_revenue': sum([p.amount_paid for p in Payment.objects.all()]),
        'today_checkins': Attendance.objects.filter(check_in_time__date=today).count(),
        'recent_payments': Payment.objects.all().order_by('-payment_date')[:5],
    }
    return render(request, 'core/admin/dashboard.html', context)


@owner_required
def manage_members(request):
    """View and manage all members - owner only"""
    members = Member.objects.all().order_by('-date_joined')
    
    # Add status to each member
    today = timezone.localtime(timezone.now()).date()
    for m in members:
        latest_payment = Payment.objects.filter(member=m).order_by('-expiration_date').first()
        if latest_payment:
            m.status = "Active" if latest_payment.expiration_date >= today else "Expired"
            m.expiration = latest_payment.expiration_date
            m.days_left = (m.expiration - today).days if m.status == "Active" else None
        else:
            m.status = "No Payment"
            m.expiration = None
            m.days_left = None
    
    context = {'members': members}
    return render(request, 'core/admin/manage_members.html', context)


@owner_required
def member_detail(request, member_id):
    """View detailed member info - owner only"""
    member = get_object_or_404(Member, id=member_id)
    payments = member.payments.all().order_by('-payment_date')
    attendances = member.attendances.all().order_by('-check_in_time')[:20]
    
    today = timezone.localtime(timezone.now()).date()
    latest_payment = payments.first()
    if latest_payment:
        member.status = "Active" if latest_payment.expiration_date >= today else "Expired"
    else:
        member.status = "No Payment"
    
    context = {
        'member': member,
        'payments': payments,
        'attendances': attendances,
    }
    return render(request, 'core/admin/member_detail.html', context)


@owner_required
def add_member(request):
    """Add new member - owner only"""
    if request.method == 'POST':
        try:
            member = Member.objects.create(
                first_name=request.POST.get('first_name'),
                last_name=request.POST.get('last_name'),
                email=request.POST.get('email', ''),
                phone_number=request.POST.get('phone_number', ''),
            )
            messages.success(request, f"Member {member.first_name} {member.last_name} added successfully!")
            return redirect('member_detail', member_id=member.id)
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return render(request, 'core/admin/add_member.html')


@owner_required
def manage_payments(request):
    """View and manage all payments - owner only"""
    payments = Payment.objects.all().order_by('-payment_date')
    
    context = {
        'payments': payments,
        'total_revenue': sum([p.amount_paid for p in payments]),
    }
    return render(request, 'core/admin/manage_payments.html', context)


@owner_required
def add_payment(request):
    """Add new payment/renewal - owner only"""
    if request.method == 'POST':
        try:
            member = Member.objects.get(id=request.POST.get('member_id'))
            plan = MembershipPlan.objects.get(id=request.POST.get('plan_id'))
            payment_date = timezone.datetime.strptime(
                request.POST.get('payment_date'), '%Y-%m-%d'
            ).date()
            
            payment = Payment.objects.create(
                member=member,
                membership_plan=plan,
                amount_paid=plan.price,
                payment_date=payment_date,
            )
            messages.success(request, f"Payment recorded for {member.first_name}!")
            return redirect('manage_payments')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    context = {
        'members': Member.objects.all(),
        'plans': MembershipPlan.objects.all(),
    }
    return render(request, 'core/admin/add_payment.html', context)


@owner_required
def manage_attendance(request):
    """View all attendance records - owner only"""
    today = timezone.localtime(timezone.now()).date()
    attendance = Attendance.objects.all().order_by('-check_in_time')
    
    # Filter by date if provided
    date_filter = request.GET.get('date')
    if date_filter:
        try:
            filter_date = timezone.datetime.strptime(date_filter, '%Y-%m-%d').date()
            attendance = attendance.filter(check_in_time__date=filter_date)
        except:
            pass
    
    context = {
        'attendance': attendance,
        'today': today,
        'today_count': Attendance.objects.filter(check_in_time__date=today).count(),
    }
    return render(request, 'core/admin/manage_attendance.html', context)


@owner_required
def manage_membership_plans(request):
    """Manage membership plans - owner only"""
    plans = MembershipPlan.objects.all().order_by('price')
    
    context = {'plans': plans}
    return render(request, 'core/admin/manage_plans.html', context)


@owner_required
def add_membership_plan(request):
    """Add new membership plan - owner only"""
    if request.method == 'POST':
        try:
            plan = MembershipPlan.objects.create(
                name=request.POST.get('name'),
                price=request.POST.get('price'),
                duration_days=request.POST.get('duration_days'),
            )
            messages.success(request, f"Plan {plan.name} added successfully!")
            return redirect('manage_membership_plans')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return render(request, 'core/admin/add_plan.html')