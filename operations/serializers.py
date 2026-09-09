from rest_framework import serializers
from .models import EmergencyAnnouncement
from complaints.models import Governorate

class EmergencyAnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyAnnouncement
        fields = '__all__'

class CreateEmergencyBannerSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True, 
        error_messages={'required': 'نص الإعلان مطلوب.'}
    )
    governorate = serializers.CharField(
        required=True, 
        error_messages={'required': 'يجب تحديد المحافظة المستهدفة أو اختيار "الكل".'}
    )

    def validate_governorate(self, value):
        # التحقق من أن المحافظة موجودة فعلاً إذا لم يختر "الكل"
        if value != "الكل":
            if not Governorate.objects.filter(name_ar=value).exists():
                raise serializers.ValidationError(f"المحافظة '{value}' غير موجودة في النظام.")
        return value