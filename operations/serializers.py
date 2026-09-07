from rest_framework import serializers
from .models import EmergencyAnnouncement

class EmergencyAnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyAnnouncement
        fields = '__all__'