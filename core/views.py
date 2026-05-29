from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from datetime import timedelta
from .models import Member, MembershipPlan, Payment, Attendance


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