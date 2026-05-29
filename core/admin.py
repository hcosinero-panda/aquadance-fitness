from django.contrib import admin
from django.contrib.admin import AdminSite
from django.utils.html import format_html
from django.urls import reverse
from datetime import timedelta
from .models import MembershipPlan, Member, Payment, Attendance


class AquafitAdminSite(AdminSite):
    site_header = "Aquafit administration"
    site_title = "Aquafit Admin"
    index_title = "Aquafit Management Hub"


admin.site.site_header = "Aquafit administration"
admin.site.site_title = "Aquafit Admin"
admin.site.index_title = "Aquafit Management Hub"


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'duration_days')
    search_fields = ('name',)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_id', 'first_name', 'last_name', 'phone_number', 'expiration_status', 'date_joined')
    search_fields = ('first_name', 'last_name', 'phone_number', 'member_id')
    readonly_fields = ('member_id', 'qr_code_display', 'expiration_info', 'photo_display')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'email', 'phone_number', 'date_joined')
        }),
        ('Photo', {
            'fields': ('photo', 'photo_display'),
            'description': 'Upload member photo for visual identification'
        }),
        ('Member ID & QR Code', {
            'fields': ('member_id', 'qr_code_display'),
            'description': 'Unique member ID and QR code for check-in'
        }),
        ('Membership Status', {
            'fields': ('expiration_info',),
            'description': 'Current membership status and expiration date'
        }),
    )
    
    def photo_display(self, obj):
        """Display member photo in admin"""
        if obj.photo:
            return format_html(
                '<img src="{}" width="150" height="150" style="border-radius: 8px;" />',
                obj.photo.url
            )
        return "No photo uploaded"
    photo_display.short_description = "Photo Preview"
    
    def qr_code_display(self, obj):
        """Display QR code image in admin"""
        qr_b64 = obj.get_qr_code_base64()
        if qr_b64:
            return format_html(
                '<img src="data:image/png;base64,{}" width="200" height="200" /><br/>'
                '<small>Member ID: <strong>{}</strong><br/>Scan this QR code for check-in</small>',
                qr_b64, obj.member_id
            )
        return "QR code library not installed"
    qr_code_display.short_description = "QR Code"
    
    def expiration_info(self, obj):
        """Display membership expiration info"""
        expiration = obj.get_expiration_date()
        if not expiration:
            return format_html('<span style="color: red;"><strong>No active membership</strong></span>')
        
        days_left = obj.get_days_until_expiration()
        if obj.is_active():
            if obj.is_expiring_soon():
                return format_html(
                    '<span style="color: orange;"><strong>EXPIRING SOON</strong></span><br/>'
                    'Expires: <strong>{}</strong><br/>'
                    'Days left: <strong>{}</strong>',
                    expiration.strftime('%B %d, %Y'),
                    days_left
                )
            else:
                return format_html(
                    '<span style="color: green;"><strong>ACTIVE</strong></span><br/>'
                    'Expires: <strong>{}</strong><br/>'
                    'Days left: <strong>{}</strong>',
                    expiration.strftime('%B %d, %Y'),
                    days_left
                )
        else:
            return format_html(
                '<span style="color: red;"><strong>EXPIRED</strong></span><br/>'
                'Expired: <strong>{}</strong>',
                expiration.strftime('%B %d, %Y')
            )
    expiration_info.short_description = "Membership Status"
    
    def expiration_status(self, obj):
        """Show expiration status in list view"""
        if obj.is_active():
            if obj.is_expiring_soon():
                return format_html('<span style="color: orange; font-weight: bold;">Expiring Soon</span>')
            return format_html('<span style="color: green; font-weight: bold;">Active</span>')
        return format_html('<span style="color: red; font-weight: bold;">Expired</span>')
    expiration_status.short_description = "Status"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('member', 'membership_plan', 'amount_paid', 'payment_date', 'expiration_date_display', 'days_valid')
    list_filter = ('payment_date', 'expiration_date', 'membership_plan')
    search_fields = ('member__first_name', 'member__last_name', 'membership_plan__name')
    readonly_fields = ('expiration_date', 'calculated_expiration_preview')
    
    fieldsets = (
        ('Member & Plan', {
            'fields': ('member', 'membership_plan')
        }),
        ('Payment Details', {
            'fields': ('amount_paid', 'payment_date')
        }),
        ('Expiration (Auto-calculated)', {
            'fields': ('expiration_date', 'calculated_expiration_preview'),
            'description': 'Expiration date is automatically calculated based on plan duration. Just select the member and plan!'
        }),
    )
    
    def calculated_expiration_preview(self, obj):
        """Show how expiration is calculated"""
        if obj.membership_plan:
            calculated = obj.payment_date + timedelta(days=obj.membership_plan.duration_days)
            return format_html(
                '<div style="padding: 10px; background: #f0f9ff; border: 1px solid #06b6d4; border-radius: 4px;">'
                '<strong>Payment Date:</strong> {}<br/>'
                '<strong>Plan Duration:</strong> {} days<br/>'
                '<strong>Auto-calculated Expiration:</strong> <span style="color: green; font-weight: bold; font-size: 16px;">{}</span>'
                '</div>',
                obj.payment_date.strftime('%B %d, %Y'),
                obj.membership_plan.duration_days,
                calculated.strftime('%B %d, %Y')
            )
        return "Select a membership plan to see expiration date"
    calculated_expiration_preview.short_description = "How It's Calculated"
    
    def expiration_date_display(self, obj):
        """Show expiration in list with color coding"""
        from django.utils import timezone as tz
        today = tz.now().date()
        if obj.expiration_date:
            if obj.expiration_date >= today:
                color = "green"
                text = "Active"
            else:
                color = "red"
                text = "Expired"
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span><br/><small>{}</small>',
                color, text, obj.expiration_date.strftime('%b %d, %Y')
            )
        return "Not set"
    expiration_date_display.short_description = "Expiration Status"
    
    def days_valid(self, obj):
        """Show number of days valid"""
        if obj.membership_plan:
            return f"{obj.membership_plan.duration_days} days"
        return "-"
    days_valid.short_description = "Plan Duration"


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('member', 'check_in_time', 'water_refills_purchased')
    list_filter = ('check_in_time',)
    search_fields = ('member__first_name', 'member__last_name')