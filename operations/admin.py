from django.contrib import admin
from .models import EmergencyAnnouncement
@admin.register(EmergencyAnnouncement)
class EmergencyAnnouncementAdmin(admin.ModelAdmin):
    list_display = ('id', 'message_ar', 'is_visible', 'created_at')
    list_filter = ('is_visible', 'created_at')
    search_fields = ('message_ar', 'message_en')
    filter_horizontal = ('governorates',)
    readonly_fields = ('created_at',)