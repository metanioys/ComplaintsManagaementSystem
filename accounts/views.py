from django.db import transaction
from rest_framework import generics, status
from rest_framework.response import Response
from .models import RewardVoucher
from django.utils import timezone
from .serializers import  BreakGlassLogSerializer, BreakGlassSerializer, DashboardLoginSerializer, RegisterSerializer,NotificationSerializer,CustomLoginSerializer,SubmitKYCSerializer,UpdateProfileSerializer, ChangePasswordSerializer,SendOTPSerializer, VerifyOTPSerializer, ResetPasswordSerializer,AdminLoginSerializer,CreateEmployeeSerializer,PendingKYCSerializer,FCMTokenSerializer
BreakGlassLogSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.views import APIView
from django.core.mail import send_mail
from .serializers import RejectKYCSerializer
from .models import AuditLog, CustomUser, OTPCode
from rest_framework.permissions import IsAuthenticated
from complaints.models import Complaint
from operations.models import EmergencyAnnouncement
from .models import KYCRequest, Notification
from rest_framework.generics import ListAPIView
from .models import UserDevice
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser 
from rest_framework.exceptions import PermissionDenied 
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True) 
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


class SendOTPView(APIView):
    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = CustomUser.objects.filter(email=email).first()
            
            if user:
                otp = OTPCode.generate_otp(user)
                
                send_mail(
                    'كود استعادة كلمة المرور',
                    f'كود التحقق الخاص بك هو: {otp.code}\nصالح لمدة 10 دقائق.',
                    'noreply@smartsys.com', 
                    [user.email],
                    fail_silently=False,
                )
            return Response({"message": "إذا كان البريد مسجلاً لدينا، فقد تم إرسال كود التحقق."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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

class ResetPasswordView(APIView):
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['code']
            new_password = serializer.validated_data['new_password']

            user = CustomUser.objects.filter(email=email).first()
            otp = OTPCode.objects.filter(user=user, code=code).last()

            if otp and otp.is_valid():
                user.set_password(new_password)
                user.save()
                
                otp.is_used = True
                otp.save()
                
                return Response({"message": "تم تغيير كلمة المرور بنجاح."}, status=status.HTTP_200_OK)
            else:
                return Response({"error": "الكود غير صحيح أو منتهي الصلاحية."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        kyc_status = "unverified"
        if user.is_kyc_verified:
            kyc_status = "verified"
        else:
            last_kyc = KYCRequest.objects.filter(citizen=user).order_by('-submitted_at').first()
            if last_kyc and last_kyc.status == 'pending':
                kyc_status = "pending"

        unread_notifications = Notification.objects.filter(user=user, is_read=False).count()

        active_count = Complaint.objects.filter(
            citizen=user,
            status__in=[Complaint.Status.NEW
                        , Complaint.Status.ASSIGNED, Complaint.Status.IN_PROGRESS]
        ).count()

        resolved_count = Complaint.objects.filter(
            citizen=user,
            status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED]
        ).count()

        announcement = EmergencyAnnouncement.objects.filter(is_visible=True).order_by('-created_at').first()
        announcement_data = None
        if announcement:
            announcement_data = {
                "is_active": True,
                "message": announcement.message_ar 
            }

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
        return Notification.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "notifications": serializer.data
        }, status=status.HTTP_200_OK)


class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
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
    parser_classes = [MultiPartParser, FormParser] 

    def post(self, request, *args, **kwargs):
        user = request.user

        if user.is_kyc_verified:
            return Response(
                {"error": "حسابك موثق مسبقاً ولا تحتاج لتقديم طلب جديد."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        has_pending = KYCRequest.objects.filter(citizen=user, status=KYCRequest.Status.PENDING).exists()
        if has_pending:
            return Response(
                {"error": "لديك طلب توثيق قيد المراجعة بالفعل، الرجاء الانتظار."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = SubmitKYCSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(citizen=user)
            
            return Response({
                "status": "success",
                "message": "تم إرسال مستنداتك للإدارة بنجاح، حسابك الآن قيد المراجعة."
            }, status=status.HTTP_200_OK)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = UpdateProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response({"message": "تم تحديث البيانات بنجاح."}, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            user = request.user
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
        
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. فقط مدير النظام يمكنه إضافة موظفين جدد.")
            
        serializer = CreateEmployeeSerializer(data=request.data)
        
        if serializer.is_valid():
            employee = serializer.save()
            
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
class AdminPendingKYCView(generics.ListAPIView):
    serializer_class = PendingKYCSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمدير النظام فقط.")
            
        return KYCRequest.objects.filter(
            status=KYCRequest.Status.PENDING
        ).select_related('citizen').order_by('submitted_at')
class AdminApproveKYCView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, kyc_id, *args, **kwargs):
        user = request.user
        
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمدير النظام فقط.")
            
        clean_kyc_id = str(kyc_id).replace('kyc-', '')

        try:
            kyc_request = KYCRequest.objects.select_related('citizen').get(id=clean_kyc_id)
        except KYCRequest.DoesNotExist:
            return Response(
                {"error": "طلب التوثيق غير موجود في النظام."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        if kyc_request.status != KYCRequest.Status.PENDING:
            return Response(
                {"error": f"لا يمكن تعديل هذا الطلب. حالته الحالية: {kyc_request.status}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            kyc_request.status = KYCRequest.Status.APPROVED
            kyc_request.reviewer = user
            kyc_request.save(update_fields=['status', 'reviewer'])
            
            citizen = kyc_request.citizen
            citizen.is_kyc_verified = True
            citizen.save(update_fields=['is_kyc_verified'])
            
            AuditLog.objects.create(
                admin=user,
                action_type="قبول توثيق KYC",
                target_citizen=citizen,
                details=f"تم قبول طلب التوثيق (الرقم الوطني: {kyc_request.national_id}) بواسطة المدير."
            )
            
            Notification.objects.create(
                user=citizen,
                title="تم توثيق حسابك بنجاح ✅",
                body="مبروك! تمت مراجعة مستنداتك والموافقة عليها. حسابك الآن موثق بالكامل."
            )

        return Response({
            "status": "success",
            "message": "تم قبول طلب التوثيق وتحديث حالة حساب المواطن بنجاح."
        }, status=status.HTTP_200_OK)
class AdminRejectKYCView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, kyc_id, *args, **kwargs):
        user = request.user
        
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمدير النظام فقط.")
            
        serializer = RejectKYCSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        reason = serializer.validated_data['reason']
            
        clean_kyc_id = str(kyc_id).replace('kyc-', '')

        try:
            kyc_request = KYCRequest.objects.select_related('citizen').get(id=clean_kyc_id)
        except KYCRequest.DoesNotExist:
            return Response(
                {"error": "طلب التوثيق غير موجود في النظام."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        if kyc_request.status != KYCRequest.Status.PENDING:
            return Response(
                {"error": f"لا يمكن تعديل هذا الطلب. حالته الحالية: {kyc_request.status}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            kyc_request.status = KYCRequest.Status.REJECTED
            kyc_request.reviewer = user
            kyc_request.save(update_fields=['status', 'reviewer'])
            
            AuditLog.objects.create(
                admin=user,
                action_type="رفض توثيق KYC",
                target_citizen=kyc_request.citizen,
                details=f"تم رفض طلب التوثيق (الرقم الوطني: {kyc_request.national_id}). السبب المذكور: {reason}"
            )
            
            Notification.objects.create(
                user=kyc_request.citizen,
                title="تم رفض طلب توثيق الحساب ❌",
                body=f"نأسف، لم نتمكن من قبول مستندات التوثيق الخاصة بك. السبب: {reason}. يرجى تقديم طلب جديد وتصحيح الأخطاء لضمان تفعيل حسابك."
            )

        return Response({
            "status": "success",
            "message": "تم رفض طلب التوثيق بنجاح وإشعار المواطن بالسبب."
        }, status=status.HTTP_200_OK)
class AdminBreakGlassView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("إنذار أمني: غير مصرح لك بكشف هويات المواطنين.")
            
        serializer = BreakGlassSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        ticket_id_raw = serializer.validated_data['targetTicketId']
        reason = serializer.validated_data['reason']
        
        clean_ticket_id = ticket_id_raw.replace('#', '')

        try:
            complaint = Complaint.objects.select_related('citizen').get(ticket_number=clean_ticket_id)
        except Complaint.DoesNotExist:
            return Response({"error": "البلاغ المطلوب غير موجود."}, status=status.HTTP_404_NOT_FOUND)
            
        citizen = complaint.citizen
        
        kyc = KYCRequest.objects.filter(citizen=citizen, status=KYCRequest.Status.APPROVED).first()
        national_id = kyc.national_id if kyc else "غير موثق (لا يوجد رقم وطني)"

        with transaction.atomic():
            AuditLog.objects.create(
                admin=user,
                action_type="كسر الزجاج (كشف هوية)",
                target_citizen=citizen,
                details=f"تنبيه أمني: تم كشف هوية مقدم البلاغ رقم #{clean_ticket_id}. السبب المدخل: {reason}"
            )

        return Response({
            "status": "success",
            "message": "تم كشف الهوية وتسجيل العملية في سجلات المراقبة الأمنية غير القابلة للحذف.",
            "citizen_data": {
                "fullName": citizen.full_name,
                "email": citizen.email,
                "nationalId": national_id
            }
        }, status=status.HTTP_200_OK)


class AdminBreakGlassLogView(generics.ListAPIView):
    serializer_class = BreakGlassLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمدير النظام فقط.")
        return AuditLog.objects.filter(
            action_type="كسر الزجاج (كشف هوية)"
        ).select_related('admin').order_by('-action_time')

class UpdateFCMTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = FCMTokenSerializer(data=request.data)
        if serializer.is_valid():
            fcm_token = serializer.validated_data['fcm_token']
            device_type = serializer.validated_data['device_type']
            user = request.user

            UserDevice.objects.update_or_create(
                fcm_token=fcm_token,
                defaults={'user': user, 'device_type': device_type}
            )

            return Response({"status": "success", "message": "تم تحديث توكن الإشعارات بنجاح."}, status=status.HTTP_200_OK)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ClaimRewardView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user
        
        points_tier = request.data.get('points_tier')
        
        if not points_tier:
            return Response({"error": "يرجى تحديد فئة النقاط المطلوبة (points_tier)."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            points_tier = int(points_tier)
        except ValueError:
            return Response({"error": "فئة النقاط يجب أن تكون رقماً."}, status=status.HTTP_400_BAD_REQUEST)

        if user.points < points_tier:
            return Response({
                "error": f"رصيد نقاطك ({user.points}) غير كافٍ لاستبدال هذه الهدية ({points_tier})."
            }, status=status.HTTP_400_BAD_REQUEST)

        voucher = RewardVoucher.objects.select_for_update().filter(
            required_points=points_tier, 
            is_claimed=False
        ).first()

        if not voucher:
            return Response({
                "error": "عذراً، نفدت الهدايا لهذه الفئة حالياً. يرجى المحاولة لاحقاً."
            }, status=status.HTTP_404_NOT_FOUND)

        voucher.is_claimed = True
        voucher.claimed_by = user
        voucher.claimed_at = timezone.now()
        voucher.save()

        user.points -= points_tier
        user.save(update_fields=['points'])

        Notification.objects.create(
            user=user,
            title="مبروك! تم استلام مكافأتك 🎁",
            body=f"تم خصم {points_tier} نقطة واستلام كود: {voucher.title}."
        )

        return Response({
            "status": "success",
            "reward_title": voucher.title,
            "code": voucher.code,
            "instructions": voucher.instructions,
            "new_points_total": user.points
        }, status=status.HTTP_200_OK)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        fcm_token = request.data.get('fcm_token')
        
        if fcm_token:
            UserDevice.objects.filter(user=request.user, fcm_token=fcm_token).delete()
            
        return Response({
            "status": "success",
            "message": "تم تسجيل الخروج ومسح توكن الإشعارات بنجاح."
        }, status=status.HTTP_200_OK)