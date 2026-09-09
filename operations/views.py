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
        
        # 🛡️ 1. الحماية: فقط مدير النظام
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمدير النظام فقط.")
            
        # 📝 2. التحقق من البيانات القادمة من الفرونت إند
        serializer = CreateEmergencyBannerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        message = serializer.validated_data['message']
        gov_name = serializer.validated_data['governorate']

        # ⚙️ 3. تنفيذ العملية بأمان
        with transaction.atomic():
            # أ. (لمسة السنيور): إخفاء أي إعلانات طوارئ سابقة لكي لا تتراكم في التطبيق
            EmergencyAnnouncement.objects.filter(is_visible=True).update(is_visible=False)

            # ب. إنشاء الإعلان الجديد
            announcement = EmergencyAnnouncement.objects.create(
                message_ar=message,
                message_en=message, # ننسخ نفس النص حالياً بما أن الفرونت لا يدعم لغتين
                is_visible=True
            )

            # ج. معالجة الاستهداف (محافظة معينة أم الكل؟)
            target_text = "الجميع (إعلان وطني)"
            if gov_name != "الكل":
                # بما أننا تحققنا من وجودها في الـ Serializer، يمكننا جلبها بأمان
                gov = Governorate.objects.get(name_ar=gov_name)
                # ربط المحافظة بالإعلان (علاقة Many-to-Many)
                announcement.governorates.add(gov)
                target_text = f"محافظة {gov_name}"

            # د. التوثيق الأمني
            AuditLog.objects.create(
                admin=user,
                action_type="إذاعة إعلان طوارئ",
                details=f"تم إصدار إعلان طوارئ يستهدف: {target_text}. النص: {message}"
            )

        # 📤 4. إرسال الرد للواجهة
        return Response({
            "status": "success",
            "message": "تم إذاعة إعلان الطوارئ بنجاح وسيبدأ بالظهور للمواطنين فوراً.",
            "target": target_text
        }, status=status.HTTP_201_CREATED)
