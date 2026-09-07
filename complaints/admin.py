from django.contrib import admin
from .models import Governorate, Category, Complaint, Attachment, ComplaintHistory

@admin.register(Governorate)
class GovernorateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name_ar', 'name_en')
    search_fields = ('name_ar', 'name_en')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name_ar', 'name_en')
    search_fields = ('name_ar', 'name_en')

# 🌟 ميزة الـ Inline لعرض المرفقات داخل الشكوى
class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0 # لا تعرض حقول إضافية فارغة
    readonly_fields = ('uploaded_at',)

# 🌟 ميزة الـ Inline لعرض تاريخ حركات الشكوى
class ComplaintHistoryInline(admin.TabularInline):
    model = ComplaintHistory
    extra = 0
    readonly_fields = ('action_by', 'assigned_to', 'old_status', 'new_status', 'notes', 'action_date')
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False # منع الإضافة اليدوية للتاريخ من الإدمن

@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'title', 'citizen', 'category', 'governorate', 'status', 'submitted_at')
    list_filter = ('status', 'category', 'governorate', 'citizen_rating', 'submitted_at')
    search_fields = ('ticket_number', 'title', 'citizen__email', 'citizen__full_name')
    readonly_fields = ('id', 'ticket_number', 'submitted_at', 'updated_at')
    # دمج الـ Inlines هنا
    inlines = [AttachmentInline, ComplaintHistoryInline]
    
    # تنسيق شكل الصفحة من الداخل
    fieldsets = (
        ('المعلومات الأساسية', {
            'fields': ('ticket_number', 'citizen', 'category', 'governorate', 'title', 'description', 'location')
        }),
        ('حالة وإدارة الشكوى', {
            'fields': ('status', 'current_assignee', 'merged_to', 'specialist_message', 'citizen_rating')
        }),
        ('التواريخ', {
            'fields': ('submitted_at', 'updated_at')
        }),
    )