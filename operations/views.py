from django.shortcuts import render

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db import transaction

from .models import EmergencyAnnouncement
from complaints.models import Governorate
from accounts.models import AuditLog
from .serializers import CreateEmergencyBannerSerializer

class AdminCreateEmergencyBannerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمدير النظام فقط.")
            
        serializer = CreateEmergencyBannerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        message = serializer.validated_data['message']
        gov_name = serializer.validated_data['governorate']

        with transaction.atomic():
            EmergencyAnnouncement.objects.filter(is_visible=True).update(is_visible=False)

            announcement = EmergencyAnnouncement.objects.create(
                message_ar=message,
                message_en=message, 
                is_visible=True
            )

            target_text = "الجميع (إعلان وطني)"
            if gov_name != "الكل":
                gov = Governorate.objects.get(name_ar=gov_name)
                announcement.governorates.add(gov)
                target_text = f"محافظة {gov_name}"

            AuditLog.objects.create(
                admin=user,
                action_type="إذاعة إعلان طوارئ",
                details=f"تم إصدار إعلان طوارئ يستهدف: {target_text}. النص: {message}"
            )

        return Response({
            "status": "success",
            "message": "تم إذاعة إعلان الطوارئ بنجاح وسيبدأ بالظهور للمواطنين فوراً.",
            "target": target_text
        }, status=status.HTTP_201_CREATED)
