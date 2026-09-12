from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth.models import Group
from accounts.models import CustomUser
from complaints.models import Governorate
from operations.models import EmergencyAnnouncement
from rest_framework_simplejwt.tokens import RefreshToken

class EmergencyBannerTests(APITestCase):
    
    def setUp(self):
        # 
        self.super_admin_group, _ = Group.objects.get_or_create(name='super_admin')
        self.citizen_group, _ = Group.objects.get_or_create(name='citizen')
        
        self.governorate = Governorate.objects.create(name_ar="دمشق", name_en="Damascus")
        
        # 3. إنشاء حساب مدير (Super Admin)
        self.admin_user = CustomUser.objects.create_user(email="admin@test.com", password="password123")
        self.admin_user.groups.add(self.super_admin_group)
        
        # 4. إنشاء حساب مواطن عادي
        self.citizen_user = CustomUser.objects.create_user(email="citizen@test.com", password="password123")
        self.citizen_user.groups.add(self.citizen_group)
        
        # رابط الـ API الذي سنختبره
        self.url = '/api/admin/emergency-banners'

    def get_jwt_token(self, user):
        """دالة مساعدة لتوليد الـ Token للمستخدمين في الاختبار"""
        refresh = RefreshToken.for_user(user)
        return f'Bearer {refresh.access_token}'

    # ------------------ بدء الاختبارات ------------------

    def test_create_banner_success_as_admin(self):
        """اختبار: مدير النظام يستطيع إنشاء إعلان بنجاح"""
        
        # وضع الـ Token الخاص بالمدير في الـ Header
        self.client.credentials(HTTP_AUTHORIZATION=self.get_jwt_token(self.admin_user))
        
        data = {
            "message": "اختبار انقطاع المياه",
            "governorate": "دمشق"
        }
        
        # إرسال الطلب (POST)
        response = self.client.post(self.url, data, format='json')
        
        # 1. التأكد أن الرد هو 201 Created
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # 2. التأكد أن الإعلان تم حفظه فعلاً في قاعدة البيانات
        self.assertEqual(EmergencyAnnouncement.objects.count(), 1)
        self.assertEqual(EmergencyAnnouncement.objects.first().message_ar, "اختبار انقطاع المياه")

    def test_create_banner_fails_without_token(self):
        """اختبار: لا يمكن الدخول بدون توكن (اختبار الأمان 1)"""
        
        # لم نقم بوضع credentials هنا
        data = {"message": "نص", "governorate": "الكل"}
        response = self.client.post(self.url, data, format='json')
        
        # التأكد أن النظام يطرد المستخدم (401 Unauthorized)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_banner_fails_as_citizen(self):
        """اختبار: المواطن لا يمكنه إذاعة طوارئ (اختبار الأمان 2)"""
        
        # وضع التوكن الخاص بالمواطن العادي
        self.client.credentials(HTTP_AUTHORIZATION=self.get_jwt_token(self.citizen_user))
        
        data = {"message": "نص", "governorate": "الكل"}
        response = self.client.post(self.url, data, format='json')
        
        # التأكد أن النظام يرفض العملية (403 Forbidden)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)