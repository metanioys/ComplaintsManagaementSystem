from django.contrib import admin
from .models import Governorate, Category, Complaint, Attachment, ComplaintHistory
from accounts.utils import send_push_notification
from accounts.models import Notification
@admin.register(Governorate)
class GovernorateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name_ar', 'name_en')
    search_fields = ('name_ar', 'name_en')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name_ar', 'name_en')
    search_fields = ('name_ar', 'name_en')

class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0 
    readonly_fields = ('uploaded_at',)

class ComplaintHistoryInline(admin.TabularInline):
    model = ComplaintHistory
    extra = 0
    readonly_fields = ('action_by', 'assigned_to', 'old_status', 'new_status', 'notes', 'action_date')
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False 
@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'title', 'citizen', 'category', 'governorate', 'status', 'submitted_at')
    list_filter = ('status', 'category', 'governorate', 'citizen_rating', 'submitted_at')
    search_fields = ('ticket_number', 'title', 'citizen__email', 'citizen__full_name')
    readonly_fields = ('id', 'ticket_number', 'submitted_at', 'updated_at')
    inlines = [AttachmentInline, ComplaintHistoryInline]
    
    fieldsets = (
    )

    def save_model(self, request, obj, form, change):
        if change:
            old_obj = Complaint.objects.get(pk=obj.pk)
            
            if old_obj.status != obj.status: 
                
                ComplaintHistory.objects.create(
                    complaint=obj,
                    action_by=request.user,
                    old_status=old_obj.status,
                    new_status=obj.status,
                    notes="تم تحديث حالة البلاغ مباشرة من قبل الإدارة (عبر لوحة التحكم)."
                )

                Notification.objects.create(
                    user=obj.citizen,
                    title="تحديث بخصوص بلاغك 📢",
                    body=f"قامت الإدارة بتحديث حالة بلاغك رقم #{obj.ticket_number}."
                )

                send_push_notification(
                    user=obj.citizen,
                    title="تحديث من الإدارة 📢",
                    body=f"تم تغيير حالة البلاغ رقم #{obj.ticket_number}، افتح التطبيق لمعرفة التفاصيل.",
                    ticket_id=obj.ticket_number
                )

        super().save_model(request, obj, form, change)