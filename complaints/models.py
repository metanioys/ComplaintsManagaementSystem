from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid
from accounts.models import CustomUser

class Governorate(models.Model):
    id = models.AutoField(primary_key=True, verbose_name=_("رقم المحافظة"))
    name_ar = models.CharField(max_length=100, verbose_name=_("الاسم بالعربي"))
    name_en = models.CharField(max_length=100, verbose_name=_("الاسم بالإنجليزي"))

class Category(models.Model):
    id = models.AutoField(primary_key=True, verbose_name=_("رقم التصنيف"))
    name_ar = models.CharField(max_length=100, verbose_name=_("الاسم بالعربي"))
    name_en = models.CharField(max_length=100, verbose_name=_("الاسم بالإنجليزي"))
class RatingChoices(models.TextChoices):
        SATISFIED = 'satisfied', _('تم الحل - راضٍ')
        UNSATISFIED = 'unsatisfied', _('إصلاح سيء - غير راضٍ')

class Complaint(models.Model):
    class Status(models.TextChoices):
        NEW = 'newStatus', _('جديدة')
        ASSIGNED = 'assigned', _('محالة للمختص')
        IN_PROGRESS = 'in_progress', _('قيد التنفيذ')
        RESOLVED = 'resolved', _('تم الحل')
        REJECTED = 'rejected', _('مرفوضة')
        CLOSED = 'closed', _('مغلقة')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name=_("المعرف الفريد"))
    ticket_number = models.CharField(max_length=50, unique=True, verbose_name=_("رقم التذكرة"))
    
    citizen = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='complaints', verbose_name=_("معرف المواطن"))
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name=_("معرف التصنيف"))
    title = models.CharField(max_length=255, verbose_name=_("عنوان الشكوى"), default="بدون عنوان")
    description = models.TextField(verbose_name=_("وصف المشكلة"))
    
    location = models.CharField(max_length=255, verbose_name=_("الموقع التفصيلي"), default="غير محدد")
    
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name=_("خط العرض"))
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name=_("خط الطول"))

    governorate = models.ForeignKey(Governorate, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("معرف المحافظة"))
    audio_file = models.FileField(upload_to='complaints_audio/', null=True, blank=True, verbose_name=_("تسجيل صوتي"))
    merged_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='duplicate_tickets', verbose_name=_("تذكرة الدمج الأساسية"))
    current_assignee = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='current_tasks', verbose_name=_("المسؤول الحالي"))
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, verbose_name=_("حالة الشكوى"))
    specialist_message = models.TextField(null=True, blank=True, verbose_name=_("رسالة تحديث المختص"))
    citizen_rating = models.CharField(max_length=20, choices=RatingChoices.choices, null=True, blank=True, verbose_name=_("تقييم المواطن"))
    
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ التقديم"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("تاريخ التحديث"))
    upvotes = models.ManyToManyField('accounts.CustomUser', related_name='upvoted_complaints', blank=True, verbose_name=_("المواطنون المتأثرون"))
    is_urgent = models.BooleanField(default=False, verbose_name=_("أولوية عاجلة"))

    def __str__(self):
        return f"{self.ticket_number} - {self.title}"
class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name=_("رقم المرفق"))

    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='attachments', verbose_name=_("معرف الشكوى"))
    file_link = models.FileField(upload_to='complaints_media/', verbose_name=_("رابط الملف"))
    file_type = models.CharField(max_length=50, verbose_name=_("نوع الملف"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الرفع"))

class ComplaintHistory(models.Model):
    id = models.AutoField(primary_key=True, verbose_name=_("رقم الحركة"))
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='history', verbose_name=_("معرف الشكوى"))
    
    action_by = models.ForeignKey(CustomUser, on_delete=models.DO_NOTHING, related_name='actions_taken', verbose_name=_("المنفذ"))
    
    assigned_to = models.ForeignKey(CustomUser, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='assigned_complaints', verbose_name=_("محالة إلى"))
    
    old_status = models.CharField(max_length=20, choices=Complaint.Status.choices, null=True, blank=True, verbose_name=_("الحالة السابقة"))
    new_status = models.CharField(max_length=20, choices=Complaint.Status.choices, verbose_name=_("الحالة الجديدة"))
    
    notes = models.TextField(null=True, blank=True, verbose_name=_("الملاحظات"))
    
    action_date = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإجراء"))
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs) 
        
        if self.assigned_to and self.assigned_to != self.complaint.current_assignee:
            self.complaint.current_assignee = self.assigned_to
            self.complaint.save(update_fields=['current_assignee'])
    class Meta:
        ordering = ['-action_date'] 

