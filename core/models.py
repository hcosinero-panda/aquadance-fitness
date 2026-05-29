from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid
import io
from base64 import b64encode


class MembershipPlan(models.Model):
    """Tracks gym membership tiers (e.g., Gym Monthly, Zumba Session, 12-Day Pass)"""
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    duration_days = models.IntegerField(help_text="Number of days this plan lasts (e.g., 30 for monthly)")

    def __str__(self):
        return f"{self.name} (₱{self.price})"


class Member(models.Model):
    """Tracks the actual gym members registered in the facility"""
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    date_joined = models.DateField(default=timezone.now)
    member_id = models.CharField(max_length=20, unique=True, editable=False, help_text="Unique member ID (e.g., MEM-001539)")
    photo = models.ImageField(upload_to='member_photos/', blank=True, null=True, help_text="Member profile photo for visual identification")

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.member_id})"
    
    def save(self, *args, **kwargs):
        """Auto-generate member_id if not set"""
        if not self.member_id:
            # Count existing members and add 1
            last_member = Member.objects.exclude(member_id='').order_by('-id').first()
            if last_member and last_member.member_id:
                try:
                    last_num = int(last_member.member_id.split('-')[1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            self.member_id = f"MEM-{new_num:06d}"
        
        super().save(*args, **kwargs)
    
    def get_qr_code_base64(self):
        """Generate QR code from member_id as base64 image"""
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=5, border=2)
            qr.add_data(self.member_id)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            return b64encode(buffer.getvalue()).decode()
        except ImportError:
            return None
    
    def get_latest_payment(self):
        """Get the most recent payment/membership"""
        return self.payments.order_by('-payment_date').first()
    
    def get_expiration_date(self):
        """Get membership expiration date"""
        latest = self.get_latest_payment()
        if latest:
            return latest.expiration_date
        return None
    
    def get_days_until_expiration(self):
        """Calculate days until expiration (None if expired/no membership)"""
        expiration = self.get_expiration_date()
        if not expiration:
            return None
        
        today = timezone.localtime(timezone.now()).date()
        days = (expiration - today).days
        return days if days >= 0 else None
    
    def is_active(self):
        """Check if member has active membership"""
        expiration = self.get_expiration_date()
        if not expiration:
            return False
        
        today = timezone.localtime(timezone.now()).date()
        return expiration >= today
    
    def is_expiring_soon(self, days=7):
        """Check if membership expires within N days"""
        days_left = self.get_days_until_expiration()
        if days_left is None:
            return False
        return 0 <= days_left <= days
    
    def is_expired(self):
        """Check if membership has expired"""
        return not self.is_active() and self.get_expiration_date() is not None


class Payment(models.Model):
    """Tracks transactions, linking members to plans and calculating expiration dates"""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='payments')
    membership_plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT)
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    
    # Changed: added blank=True, null=True so Django Admin allows saving without manual typing
    expiration_date = models.DateField(
        blank=True, 
        null=True, 
        help_text="Automatically calculated from the chosen plan's duration if left blank."
    )

    def save(self, *args, **kwargs):
        # AUTOMATIC MATH RULE: If expiration_date isn't typed in, calculate it!
        if not self.expiration_date and self.membership_plan:
            # Adds the plan's duration_days directly to the payment_date
            self.expiration_date = self.payment_date + timedelta(days=self.membership_plan.duration_days)
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment: {self.member} - {self.membership_plan.name}"


class Attendance(models.Model):
    """Tracks daily check-ins and secondary purchases like water refills"""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='attendances')
    check_in_time = models.DateTimeField(default=timezone.now)
    water_refills_purchased = models.IntegerField(default=0, help_text="Number of ₱10 refills during this session")

    def __str__(self):
        local_time = timezone.localtime(self.check_in_time)
        return f"{self.member} checked in at {local_time.strftime('%Y-%m-%d %I:%M %p')}"