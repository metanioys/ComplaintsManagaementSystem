from django.contrib import admin
from .models import CustomUser, KYCRequest, AuditLog, OTPCode, Notification

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    # الحقول التي تظهر في الجدول
    list_display = ('email', 'full_name', 'points', 'is_kyc_verified', 'is_staff', 'is_active')
    # الفلاتر الجانبية
    list_filter = ('is_kyc_verified', 'is_staff', 'is_superuser', 'is_active', 'groups')
    # شريط البحث
    search_fields = ('email', 'full_name')
    # الحقول التي تدعم الاختيار المتعدد بشكل أنيق
    filter_horizontal = ('managed_governorates', 'managed_categories', 'groups', 'user_permissions')
    ordering = ('-date_joined',)

@admin.register(KYCRequest)
class KYCRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'citizen', 'national_id', 'status', 'reviewer', 'submitted_at')
    list_filter = ('status', 'submitted_at')
    search_fields = ('national_id', 'citizen__email', 'citizen__full_name')
    # جعل بعض الحقول للقراءة فقط لتجنب التلاعب
    readonly_fields = ('submitted_at',)

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'admin', 'action_type', 'target_citizen', 'action_time')
    list_filter = ('action_type', 'action_time')
    search_fields = ('admin__email', 'details')
    # سجل التدقيق يجب أن يكون للقراءة فقط (حماية أمنية)
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'is_used', 'created_at')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__email', 'code')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__email', 'title', 'body')