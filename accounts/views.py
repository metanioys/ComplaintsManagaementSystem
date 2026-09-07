from rest_framework import generics, status
from rest_framework.response import Response
from .serializers import DashboardLoginSerializer, RegisterSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomLoginSerializer
from rest_framework.views import APIView
from django.core.mail import send_mail
from .models import CustomUser, OTPCode
from rest_framework.permissions import IsAuthenticated
from complaints.models import Complaint
from operations.models import EmergencyAnnouncement
from .models import KYCRequest, Notification
from rest_framework.generics import ListAPIView
from .models import Notification
from .serializers import NotificationSerializer
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import SubmitKYCSerializer
from rest_framework.exceptions import PermissionDenied
from .serializers import CreateEmployeeSerializer
from .serializers import UpdateProfileSerializer, ChangePasswordSerializer,SendOTPSerializer, VerifyOTPSerializer, ResetPasswordSerializer,AdminLoginSerializer
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True) # يتأكد من صحة البيانات وأن الإيميل غير مسجل مسبقاً
        user = serializer.save()
        
        return Response({
            "status": "success",
            "message": "تم إنشاء الحساب بنجاح",
            "data": {
                "full_name": user.full_name,
                "email": user.email
            }
        }, status=status.HTTP_201_CREATED)
    
class LoginView(TokenObtainPairView):
    serializer_class = CustomLoginSerializer


# 1. إرسال الكود
class SendOTPView(APIView):
    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = CustomUser.objects.filter(email=email).first()
            
            if user:
                # توليد الكود
                otp = OTPCode.generate_otp(user)
                
                # إرسال الإيميل
                send_mail(
                    'كود استعادة كلمة المرور',
                    f'كود التحقق الخاص بك هو: {otp.code}\nصالح لمدة 10 دقائق.',
                    'noreply@smartsys.com', # إيميل المرسل (نظامك)
                    [user.email],
                    fail_silently=False,
                )
            # نرجع رسالة نجاح سواء كان الإيميل موجود أو لا (لحماية النظام من تخمين الإيميلات)
            return Response({"message": "إذا كان البريد مسجلاً لدينا، فقد تم إرسال كود التحقق."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 2. التحقق من الكود (للانتقال لواجهة تعيين كلمة المرور)
class VerifyOTPView(APIView):
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['code']
            
            user = CustomUser.objects.filter(email=email).first()
            if not user:
                return Response({"error": "المستخدم غير موجود."}, status=status.HTTP_404_NOT_FOUND)

            otp = OTPCode.objects.filter(user=user, code=code).last()
            
            if otp and otp.is_valid():
                return Response({"message": "كود صحيح، يمكنك الآن تغيير كلمة المرور."}, status=status.HTTP_200_OK)
            else:
                return Response({"error": "الكود غير صحيح أو منتهي الصلاحية."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 3. تعيين كلمة المرور الجديدة
class ResetPasswordView(APIView):
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['code']
            new_password = serializer.validated_data['new_password']

            user = CustomUser.objects.filter(email=email).first()
            otp = OTPCode.objects.filter(user=user, code=code).last()

            # نتحقق من الكود مرة أخيرة للأمان
            if otp and otp.is_valid():
                # تغيير كلمة المرور
                user.set_password(new_password)
                user.save()
                
                # حرق الكود لكي لا يستخدم مرة أخرى
                otp.is_used = True
                otp.save()
                
                return Response({"message": "تم تغيير كلمة المرور بنجاح."}, status=status.HTTP_200_OK)
            else:
                return Response({"error": "الكود غير صحيح أو منتهي الصلاحية."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# أضف هذا الكلاس في نهاية الملف
class DashboardSummaryView(APIView):
    # لا يمكن الدخول هنا إلا إذا كان المستخدم مسجل دخوله (يمتلك Token)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 1. تحديد حالة توثيق الحساب (KYC Status)
        kyc_status = "unverified"
        if user.is_kyc_verified:
            kyc_status = "verified"
        else:
            # نبحث عن آخر طلب توثيق قدمه المواطن
            last_kyc = KYCRequest.objects.filter(citizen=user).order_by('-submitted_at').first()
            if last_kyc and last_kyc.status == 'pending':
                kyc_status = "pending"

        # 2. حساب الإشعارات غير المقروءة
        unread_notifications = Notification.objects.filter(user=user, is_read=False).count()

        # 3. إحصائيات البلاغات (الشكاوى) الخاصة بهذا المواطن فقط
        active_count = Complaint.objects.filter(
            citizen=user,
            status__in=[Complaint.Status.new
                        , Complaint.Status.ASSIGNED, Complaint.Status.IN_PROGRESS]
        ).count()

        resolved_count = Complaint.objects.filter(
            citizen=user,
            status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED]
        ).count()

        # 4. جلب إعلانات الطوارئ (نجلب أحدث إعلان فعال)
        announcement = EmergencyAnnouncement.objects.filter(is_visible=True).order_by('-created_at').first()
        announcement_data = None
        if announcement:
            announcement_data = {
                "is_active": True,
                "message": announcement.message_ar # سنرسل الرسالة بالعربية للواجهة
            }

        # 5. تجميع البيانات بالشكل الذي طلبه "توني" (الفرونت إند)
        data = {
            "user_info": {
                "full_name": user.full_name,
                "points": user.points,
                "kyc_status": kyc_status,
                "unread_notifications_count": unread_notifications
            },
            "complaints_stats": {
                "active_count": active_count,
                "resolved_count": resolved_count
            },
            "emergency_announcement": announcement_data
        }

        return Response(data, status=status.HTTP_200_OK)

class NotificationListView(ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # الأمان أولاً: نجلب إشعارات المستخدم الذي قام بتسجيل الدخول فقط!
        return Notification.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        # قمنا بعمل Override لهذه الدالة لكي نطابق شكل الـ JSON الذي طلبه توني بالضبط
        # توني طلب أن تكون المصفوفة بداخل متغير اسمه "notifications"
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "notifications": serializer.data
        }, status=status.HTTP_200_OK)


# --------------------------------------------------------
# 2. Endpoint: جعل الإشعار "مقروء"
# --------------------------------------------------------
class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    # توني قال (PATCH أو POST)، لذا سنبرمج دالة patch ونستدعيها أيضاً في post لضمان المرونة
    def patch(self, request, pk):
        # نبحث عن الإشعار بشرط أن يكون الـ id مطابقاً، وأن يكون صاحبه هو المستخدم الحالي (أمان)
        try:
            notification = Notification.objects.get(id=pk, user=request.user)
            notification.is_read = True
            notification.save()
            return Response({"message": "تم تحديث حالة الإشعار بنجاح"}, status=status.HTTP_200_OK)
        except Notification.DoesNotExist:
            return Response({"error": "الإشعار غير موجود أو لا تملك صلاحية الوصول إليه"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, pk):
        return self.patch(request, pk)


class SubmitKYCView(APIView):
    permission_classes = [IsAuthenticated]
    # هذه الخطوة مهمة جداً لكي يتمكن السيرفر من قراءة الصور (Form-Data)
    parser_classes = [MultiPartParser, FormParser] 

    def post(self, request, *args, **kwargs):
        user = request.user

        # 1. حماية: التحقق مما إذا كان المستخدم موثقاً بالفعل
        if user.is_kyc_verified:
            return Response(
                {"error": "حسابك موثق مسبقاً ولا تحتاج لتقديم طلب جديد."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. حماية: التحقق مما إذا كان لديه طلب "قيد المراجعة" لم يتم الرد عليه بعد
        has_pending = KYCRequest.objects.filter(citizen=user, status=KYCRequest.Status.PENDING).exists()
        if has_pending:
            return Response(
                {"error": "لديك طلب توثيق قيد المراجعة بالفعل، الرجاء الانتظار."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. التحقق من صحة البيانات القادمة من الفرونت إند
        serializer = SubmitKYCSerializer(data=request.data)
        if serializer.is_valid():
            # حفظ الطلب وربطه بالمواطن الذي قام بتسجيل الدخول (request.user)
            serializer.save(citizen=user)
            
            # الرد المطابق لما طلبه توني في ملف الـ JSON
            return Response({
                "status": "success",
                "message": "تم إرسال مستنداتك للإدارة بنجاح، حسابك الآن قيد المراجعة."
            }, status=status.HTTP_200_OK)
            
        # في حال وجود خطأ (مثل الرقم الوطني ليس 11 رقم، أو الصور غير موجودة)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 1. كلاس تحديث الاسم
class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = UpdateProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # هنا السحر: نرجع المستخدم الذي قام بتسجيل الدخول مباشرة من التوكن
        return self.request.user

    def update(self, request, *args, **kwargs):
        # نستخدم دالة التحديث الافتراضية، ثم نرجع رسالة نجاح
        super().update(request, *args, **kwargs)
        return Response({"message": "تم تحديث البيانات بنجاح."}, status=status.HTTP_200_OK)


# 2. كلاس تغيير كلمة المرور
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # نمرر request في الـ context لكي نتمكن من جلب المستخدم داخل الـ Serializer
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            user = request.user
            # تغيير كلمة المرور (تقوم بتشفيرها تلقائياً)
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            return Response({
                "status": "success",
                "message": "تم تغيير كلمة المرور بنجاح."
            }, status=status.HTTP_200_OK)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminLoginView(TokenObtainPairView):

    serializer_class = AdminLoginSerializer



class DashboardLoginView(TokenObtainPairView):
    serializer_class = DashboardLoginSerializer


class CreateEmployeeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        
        # 🛡️ 1. الحماية: التأكد أن من يقوم بالطلب هو مدير النظام (Super Admin) حصراً
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. فقط مدير النظام يمكنه إضافة موظفين جدد.")
            
        # 2. تمرير البيانات للـ Serializer
        serializer = CreateEmployeeSerializer(data=request.data)
        
        if serializer.is_valid():
            # حفظ الموظف الجديد في قاعدة البيانات
            employee = serializer.save()
            
            # 3. إرسال رد احترافي للفرونت إند
            return Response({
                "status": "success",
                "message": "تم إضافة الموظف بنجاح.",
                "employee": {
                    "id": str(employee.id),
                    "name": employee.full_name,
                    "email": employee.email,
                    "role": request.data.get('role')
                }
            }, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)