from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
import uuid

# 1. إنشاء مدير مستخدمين مخصص يعتمد على الإيميل
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('يجب إدخال البريد الإلكتروني'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)

# 2. تعديل نموذج المستخدم
class CustomUser(AbstractUser):
    # حذف حقل الـ username الافتراضي
    username = None 
    full_name = models.CharField(max_length=255, verbose_name=_("الاسم الكامل"), default="") 
    # حذف حقل الـ role النصي لأننا سنعتمد على Groups

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name=_("الرقم التعريفي"))
    email = models.EmailField(_('البريد الإلكتروني'), unique=True)
    points = models.IntegerField(default=0, verbose_name=_("النقاط"))
    is_kyc_verified = models.BooleanField(default=False, verbose_name=_("موثق KYC"))
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = [] # لا يوجد حقول إضافية إجبارية غير الإيميل والباسورد
# إضافة قطاع الموظف (للمختصين وموظفي الفرز)
    managed_governorates = models.ManyToManyField('complaints.Governorate', blank=True, verbose_name=_("المحافظات المسؤولة"))
    managed_categories = models.ManyToManyField('complaints.Category', blank=True, verbose_name=_("التصنيفات المسؤولة"))
    objects = CustomUserManager()

    def __str__(self):
        return self.email

# (باقي كود الـ models الخاص بـ KYCRequest و AuditLog يبقى كما هو تماماً كما كتبناه سابقاً)
class KYCRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('قيد المراجعة')
        APPROVED = 'approved', _('مقبول')
        REJECTED = 'rejected', _('مرفوض')

    id = models.AutoField(primary_key=True, verbose_name=_("رقم الطلب"))
    citizen = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='kyc_requests', verbose_name=_("معرف المواطن"))
    national_id = models.CharField(max_length=20, unique=True, verbose_name=_("الرقم الوطني"))
    front_id_image = models.ImageField(upload_to='kyc/front/', verbose_name=_("صورة الهوية أمامي"))
    back_id_image = models.ImageField(upload_to='kyc/back/', verbose_name=_("صورة الهوية خلفي"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name=_("حالة الطلب"))
    reviewer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_kyc', verbose_name=_("المدير المراجع"))
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ التقديم"))

class AuditLog(models.Model):
    id = models.AutoField(primary_key=True, verbose_name=_("رقم السجل"))
    admin = models.ForeignKey(CustomUser, on_delete=models.DO_NOTHING, related_name='audit_logs', verbose_name=_("معرف المدير"))
    action_type = models.CharField(max_length=255, verbose_name=_("نوع الإجراء"))
    target_citizen = models.ForeignKey(CustomUser, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='targeted_logs', verbose_name=_("المواطن المستهدف"))
    details = models.TextField(verbose_name=_("التفاصيل"))
    action_time = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإجراء"))

# داخل accounts/models.py (أضفه في النهاية)
import random
from django.utils import timezone
from datetime import timedelta

class OTPCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='otp_codes')
    code = models.CharField(max_length=6, verbose_name=_("كود التحقق"))
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        # الكود صالح لمدة 10 دقائق فقط ولم يتم استخدامه مسبقاً
        expiration_time = self.created_at + timedelta(minutes=10)
        return timezone.now() <= expiration_time and not self.is_used

    @classmethod
    def generate_otp(cls, user):
        code = str(random.randint(100000, 999999))
        return cls.objects.create(user=user, code=code)

class Notification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications', verbose_name=_("المستخدم"))
    title = models.CharField(max_length=255, verbose_name=_("العنوان"))
    body = models.TextField(verbose_name=_("نص الإشعار"))
    is_read = models.BooleanField(default=False, verbose_name=_("مقروء"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))

    class Meta:
        ordering = ['-created_at'] # الترتيب من الأحدث للأقدم
class UserDevice(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='devices', verbose_name=_("المستخدم"))
    fcm_token = models.CharField(max_length=255, unique=True, verbose_name=_("توكن الجهاز"))
    device_type = models.CharField(max_length=20, default='android', verbose_name=_("نوع الجهاز"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.device_type}"
class RewardVoucher(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255, verbose_name=_("عنوان الهدية"))
    code = models.CharField(max_length=100, unique=True, verbose_name=_("كود الهدية (Voucher)"))
    required_points = models.IntegerField(verbose_name=_("النقاط المطلوبة"))
    instructions = models.TextField(verbose_name=_("تعليمات الاستخدام"), default="يرجى إدخال هذا الكود في تطبيق المزود الخاص بك.")
    
    is_claimed = models.BooleanField(default=False, verbose_name=_("تم الاستلام؟"))
    claimed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='claimed_rewards', verbose_name=_("المواطن المستلم"))
    claimed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("تاريخ الاستلام"))

    def __str__(self):
        return f"{self.title} - {self.required_points} نقطة"