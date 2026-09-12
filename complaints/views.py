from rest_framework.views import APIView, PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Complaint, Category, Attachment,ComplaintHistory
from .serializers import ComplaintDetailSerializer, CreateComplaintSerializer, DispatcherNewTicketSerializer, LiaisonInboxSerializer, TicketHistoryTimelineSerializer, VerifyComplaintSerializer
from .serializers import MergeTicketsSerializer,SendUpdateSerializer
import random
from accounts.utils import send_push_notification
from django.db.models import Count
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from .serializers import EvaluateComplaintSerializer,Tier1NewTicketSerializer
from .models import RatingChoices
from rest_framework import generics
from django.db.models import Q
from .serializers import ComplaintListSerializer
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from accounts.models import CustomUser,Notification

class CreateComplaintView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        serializer = CreateComplaintSerializer(data=request.data)
        
        if serializer.is_valid():
            # 2. توليد رقم تذكرة فريد (مثال: CMT-850)
            ticket_id = f"CMT-{random.randint(100, 99999)}"
            
            # 3. معالجة التصنيف (نبحث عن التصنيف بالاسم، أو نضعه في تصنيف عام إذا لم نجده)
            category_name = serializer.validated_data.pop('category_name')
            category, _ = Category.objects.get_or_create(
                name_en=category_name, 
                defaults={'name_ar': 'تصنيف عام'}
            )

            # 4. حفظ الشكوى الجديدة
            complaint = Complaint.objects.create(
                citizen=request.user,
                ticket_number=ticket_id,
                category=category,
                status=Complaint.Status.NEW,
                **serializer.validated_data
            )

            # 5. معالجة الصور المتعددة (الحد الأقصى 3 كما طلب توني)
            images = request.FILES.getlist('images')
            for index, image in enumerate(images):
                if index >= 3: # حماية: تجاهل أي صور تزيد عن 3
                    break
                Attachment.objects.create(
                    complaint=complaint,
                    file_link=image,
                    file_type=image.content_type
                )

            # 6. الرد بنفس الشكل الذي طلبه توني
            return Response({
                "status": "success",
                "message": "تم إرسال البلاغ للجهات المختصة بنجاح.",
                "ticket_id": ticket_id
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ComplaintListView(generics.ListAPIView):
    serializer_class = ComplaintListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 1. نجلب فقط شكاوى المواطن الذي قام بتسجيل الدخول (أمان 100%)
        queryset = Complaint.objects.filter(citizen=self.request.user).order_by('-submitted_at')
        
        # 2. فلترة حسب الحالة (إذا طلب توني status=active)
        status_param = self.request.query_params.get('status', None)
        if status_param == 'active':
            queryset = queryset.filter(status__in=[
                Complaint.Status.NEW, 
                Complaint.Status.ASSIGNED, 
                Complaint.Status.IN_PROGRESS
            ])
            
        # 3. فلترة حسب البحث (إذا طلب توني search=كلمة)
        search_param = self.request.query_params.get('search', None)
        if search_param:
            queryset = queryset.filter(
                Q(ticket_number__icontains=search_param) | 
                Q(title__icontains=search_param)
            )
            
        return queryset

    def list(self, request, *args, **kwargs):
        # قمنا بعمل Override لهذه الدالة لكي نغلف المصفوفة بكلمة "complaints" كما صممها توني
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "complaints": serializer.data
        }, status=status.HTTP_200_OK)

class ComplaintDetailView(generics.RetrieveAPIView):
    serializer_class = ComplaintDetailSerializer
    permission_classes = [IsAuthenticated]
    
    # هذه الخطوة مهمة جداً: نخبر جانغو أن يبحث برقم التذكرة وليس بالـ ID (الـ UUID)
    lookup_field = 'ticket_number' 

    def get_queryset(self):
        # حماية أمنية: المواطن لا يمكنه جلب إلا التذاكر التي تخصه هو فقط
        return Complaint.objects.filter(citizen=self.request.user)


class EvaluateComplaintView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_number):
        # 1. جلب الشكوى الخاصة بالمواطن
        try:
            complaint = Complaint.objects.get(ticket_number=ticket_number, citizen=request.user)
        except Complaint.DoesNotExist:
            return Response(
                {"error": "البلاغ غير موجود أو لا تملك صلاحية الوصول إليه."}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 2. التحقق من حالة الشكوى (يجب أن تكون "تم الحل" ليتم تقييمها)
        if complaint.status != Complaint.Status.RESOLVED:
            return Response(
                {"error": "لا يمكن تقييم هذا البلاغ لأنه ليس في حالة 'تم الحل'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 3. التحقق من أنه لم يقم بالتقييم مسبقاً
        if complaint.citizen_rating:
            return Response(
                {"error": "لقد قمت بتقييم هذا البلاغ مسبقاً."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. معالجة التقييم
        serializer = EvaluateComplaintSerializer(data=request.data)
        if serializer.is_valid():
            is_fixed = serializer.validated_data['is_fixed']
            user = request.user

            if is_fixed:
                # 🟩 المواطن راضٍ: نغلق التذكرة ونمنحه النقاط
                complaint.status = Complaint.Status.CLOSED
                complaint.citizen_rating = RatingChoices.SATISFIED
                user.points += 10
                user.save()
                message = "شكراً لتقييمك، تمت إضافة 10 نقاط لرصيدك."
            else:
                # 🟥 المواطن غير راضٍ: نعيد التذكرة للمختص ليراجعها
                complaint.status = Complaint.Status.ASSIGNED
                complaint.citizen_rating = RatingChoices.UNSATISFIED
                message = "نأسف لعدم رضاك، تم إعادة البلاغ للمختص للمراجعة فوراً."
            
            # حفظ التعديلات على الشكوى
            complaint.save()

            # الرد المطابق لطلب توني
            return Response({
                "status": "success",
                "message": message,
                "new_points_total": user.points
            }, status=status.HTTP_200_OK)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class Tier1NewTicketsView(generics.ListAPIView):
    serializer_class = Tier1NewTicketSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # 🛡️ حماية: التأكد أن المستخدم مأمور فرز أو مدير
        is_tier1 = user.groups.filter(name='tier1_dispatcher').exists()
        if not (is_tier1 or user.is_superuser):
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمأمور الفرز.")
            
        # جلب الشكاوى التي حالتها "جديدة" فقط
        return Complaint.objects.filter(status=Complaint.Status.NEW).order_by('submitted_at')

    def list(self, request, *args, **kwargs):
        # إرسال البيانات كمصفوفة مباشرة [{}, {}] لتتطابق مع طلب توني
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class Tier1AssignTicketView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, ticket_id):
        user = request.user
        
        # 🛡️ 1. الحماية: التأكد أن المستخدم مأمور فرز أو مدير
        is_tier1 = user.groups.filter(name='tier1_dispatcher').exists()
        if not (is_tier1 or user.is_superuser):
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمأمور الفرز.")
            
        # 🎟️ 2. جلب الشكوى (وإزالة رمز # إذا أرسله الفرونت إند بالخطأ في الرابط)
        clean_ticket_id = ticket_id.replace('#', '')
        complaint = get_object_or_404(Complaint, ticket_number=clean_ticket_id)
        
        # ⚠️ 3. التحقق من حالة الشكوى (يجب أن تكون جديدة ليتم إحالتها)
        if complaint.status != Complaint.Status.NEW:
            return Response(
                {"error": "لا يمكن إحالة هذه الشكوى لأنها ليست في حالة 'جديدة'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # 👤 4. جلب الموظف المحال إليه (Tier 2)
        assignee_id = request.data.get('assigneeId')
        if not assignee_id:
            return Response({"error": "يجب توفير assigneeId"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # هنا نفترض أن توني أرسل الـ UUID الخاص بالموظف
            assignee = CustomUser.objects.get(id=assignee_id)
        except (CustomUser.DoesNotExist, ValueError):
            return Response(
                {"error": "الموظف أو القسم المطلوب غير موجود في النظام. تأكد من إرسال الـ ID الصحيح."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        # 🔄 5. تحديث الشكوى وتوثيق الحركة (الـ Magic يحدث هنا)
        old_status = complaint.status
        
        # نغير حالة الشكوى إلى assigned
        complaint.status = Complaint.Status.ASSIGNED
        complaint.save(update_fields=['status']) # تحديث الحقل فقط لسرعة الأداء
        
        # ننشئ سجل الحركة (بفضل كودك السابق، هذا السجل سيقوم تلقائياً بتحديث current_assignee في الشكوى)
        ComplaintHistory.objects.create(
            complaint=complaint,
            action_by=user,          # مأمور الفرز الذي قام بالعملية
            assigned_to=assignee,    # ضابط الارتباط (Tier 2) الذي استلمها
            old_status=old_status,
            new_status=Complaint.Status.ASSIGNED,
            notes="تمت الإحالة من قبل مأمور الفرز إلى القسم المختص."
        )
        
        # 📤 6. إرسال الرد للفرونت إند
        return Response({
            "status": "success",
            "message": "تم إحالة الشكوى بنجاح.",
            "ticket_status": complaint.status
        }, status=status.HTTP_200_OK)


class DispatcherNewTicketsView(generics.ListAPIView):
    serializer_class = DispatcherNewTicketSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # 🛡️ 1. الحماية: التأكد أن المستخدم مأمور فرز أو مدير
        allowed_roles = ['tier1_dispatcher', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمأمور الفرز.")
            
        # 🚀 2. جلب البيانات بأقصى سرعة (Database Optimization)
        # نستخدم select_related للعلاقات الفردية (Foreign Keys)
        # و prefetch_related للعلاقات المتعددة (Many-to-Many / Reverse Foreign Keys)
        return Complaint.objects.filter(
            status=Complaint.Status.NEW
        ).select_related(
            'governorate', 'category', 'citizen'
        ).prefetch_related(
            'attachments', 'citizen__kyc_requests'
        ).order_by('submitted_at')

    def list(self, request, *args, **kwargs):
        # 3. إرسال البيانات كمصفوفة مباشرة [{}, {}] لتتطابق مع طلب توني
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)



class DispatcherAssignTicketView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, ticket_id):
        user = request.user
        
        # 🛡️ 1. الحماية: التأكد أن المستخدم مأمور فرز أو مدير
        allowed_roles = ['tier1_dispatcher', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمأمور الفرز.")
            
        # 🎟️ 2. جلب الشكوى (وإزالة رمز # إذا قام الفرونت إند بإرساله في الرابط)
        clean_ticket_id = ticket_id.replace('#', '')
        complaint = get_object_or_404(Complaint, ticket_number=clean_ticket_id)
        
        # ⚠️ 3. التحقق من حالة الشكوى (يجب أن تكون جديدة ليتم إحالتها)
        if complaint.status != Complaint.Status.NEW:
            return Response(
                {"error": "لا يمكن إحالة هذه الشكوى لأنها ليست في حالة 'جديدة'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # 👤 4. جلب معرف الموظف المحال إليه (Tier 2)
        # نقبل المفتاحين لكي لا ينكسر كود توني سواء استخدم assigneeId أو assigneeDepartment
        assignee_input = request.data.get('assigneeId') or request.data.get('assigneeDepartment')
        
        if not assignee_input:
            return Response(
                {"error": "يجب إرسال معرف خبير الصيانة (assigneeId)."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            # نتوقع هنا أن توني يرسل الـ UUID الخاص بالمستخدم
            assignee = CustomUser.objects.get(id=assignee_input)
            
            # (اختياري كحماية إضافية) التأكد أن الموظف المحال إليه هو فعلاً خبير صيانة
            if not assignee.groups.filter(name='tier2_liaison').exists():
                return Response(
                    {"error": "الموظف المحدد ليس خبير صيانة (Tier 2)."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except (CustomUser.DoesNotExist, ValueError):
            return Response(
                {"error": "خبير الصيانة المطلوب غير موجود في النظام. تأكد من إرسال المعرف (ID) الصحيح."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        # 🔄 5. تحديث الشكوى وتوثيق الحركة
        old_status = complaint.status
        complaint.status = Complaint.Status.ASSIGNED
        complaint.current_assignee = assignee # تعيين خبير الصيانة
        # نستخدم update_fields لتحسين الأداء
        complaint.save(update_fields=['status', 'current_assignee']) 
       # 📝 6. إنشاء سجل الحركة
        ComplaintHistory.objects.create(
            complaint=complaint,
            action_by=user,          
            assigned_to=assignee,    
            old_status=old_status,
            new_status=Complaint.Status.ASSIGNED,
            notes="تمت الإحالة من قبل مأمور الفرز إلى خبير الصيانة."
        )

        # 🚀 7. إشعار المواطن بأن بلاغه يتحرك (UX ممتاز)
        # لم نقم بإنشاء Notification داخلي هنا لكي لا نزعج المواطن بكثرة الإشعارات الداخلية، 
        # نكتفي بإشعار الهاتف اللطيف (Push)
        send_push_notification(
            user=complaint.citizen,
            title="بلاغك قيد الاهتمام 🏃",
            body=f"تم تحويل بلاغك رقم #{complaint.ticket_number} إلى فريق الصيانة المختص وهو الآن قيد المعالجة.",
            ticket_id=complaint.ticket_number
        )
        
        # 📤 8. الرد المطابق لما طلبه توني
        return Response({
            "status": "success",
            "message": "تم إحالة الشكوى لخبير الصيانة بنجاح."
        }, status=status.HTTP_200_OK)
class DispatcherUpdateTicketStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, ticket_id):
        user = request.user
        
        # 🛡️ 1. الحماية: التأكد أن المستخدم مأمور فرز أو مدير
        allowed_roles = ['tier1_dispatcher', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمأمور الفرز.")
            
        # 🎟️ 2. جلب الشكوى (وتنظيف الرابط من رمز # إن وُجد)
        clean_ticket_id = ticket_id.replace('#', '')
        complaint = get_object_or_404(Complaint, ticket_number=clean_ticket_id)
        
        # ⚠️ 3. استلام الحالة الجديدة والتحقق منها
        new_status = request.data.get('status')
        
        # مأمور الفرز يحق له فقط الرفض أو الإغلاق من هذه الواجهة
        valid_statuses = [Complaint.Status.REJECTED, Complaint.Status.CLOSED]
        
        if new_status not in valid_statuses:
            return Response(
                {"error": "حالة غير صالحة. يرجى إرسال 'rejected' أو 'closed'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # 🔄 4. تحديث الشكوى وتوثيق الحركة
        old_status = complaint.status
        
        # لا داعي لتغيير الحالة إذا كانت هي نفسها
        if old_status == new_status:
            return Response(
                {"message": f"الشكوى بالفعل في حالة {new_status}."}, 
                status=status.HTTP_200_OK
            )

        complaint.status = new_status
        complaint.save(update_fields=['status']) 
        
        # 📝 5. إنشاء سجل الحركة لضمان المساءلة
        notes = "تم رفض الشكوى لاعتبارها وهمية/غير صالحة." if new_status == 'rejected' else "تم إغلاق الشكوى."
        ComplaintHistory.objects.create(
            complaint=complaint,
            action_by=user,          
            old_status=old_status,
            new_status=new_status,
            notes=notes
        )
        
        return Response({
            "status": "success",
            "message": f"تم تغيير حالة الشكوى إلى {new_status} بنجاح."
        }, status=status.HTTP_200_OK)

class LiaisonInboxView(generics.ListAPIView):
    serializer_class = LiaisonInboxSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        allowed_roles = ['tier2_liaison', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لخبراء الصيانة وضباط الارتباط.")
            
        return Complaint.objects.filter(
            current_assignee=user,
            status__in=[Complaint.Status.ASSIGNED, Complaint.Status.IN_PROGRESS]
        ).select_related(
            'governorate', 'category', 'citizen', 'current_assignee'
        ).prefetch_related(
            'attachments', 
            'citizen__kyc_requests', 
            'duplicate_tickets', 
            'history'            
        ).order_by('-updated_at') 

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
class MergeTicketsView(APIView):
     permission_classes = [IsAuthenticated]

     def post(self, request, *args, **kwargs):
        user = request.user

        # 🛡️ 1. الحماية: التأكد أن المستخدم يمتلك صلاحية الدمج
        allowed_roles = ['tier1_dispatcher', 'tier2_liaison', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك بإجراء عملية الدمج.")

        # 📝 2. استخدام الـ Serializer للتحقق من البيانات
        serializer = MergeTicketsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # استخراج البيانات بعد التأكد من صحتها
        primary_id_raw = serializer.validated_data['primaryTicketId']
        tickets_to_merge_raw = serializer.validated_data['ticketIdsToMerge']

        # تنظيف الأرقام من رمز #
        primary_ticket_number = primary_id_raw.replace('#', '')
        tickets_to_merge_numbers = [t.replace('#', '') for t in tickets_to_merge_raw]

        # 🔍 3. جلب التذكرة الأساسية
        try:
            primary_ticket = Complaint.objects.get(ticket_number=primary_ticket_number)
        except Complaint.DoesNotExist:
            return Response(
                {"error": f"التذكرة الأساسية {primary_id_raw} غير موجودة."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 🔍 4. جلب التذاكر المراد دمجها
        tickets_to_merge = Complaint.objects.filter(ticket_number__in=tickets_to_merge_numbers)
        
        if not tickets_to_merge.exists():
            return Response(
                {"error": "لم يتم العثور على أي من التذاكر المطلوب دمجها في النظام."},
                status=status.HTTP_404_NOT_FOUND
            )

        # ⚙️ 5. إجراء الدمج داخل Database Transaction لضمان أمان البيانات
        with transaction.atomic():
            # أ. تحديث التذكرة الأساسية
            old_primary_status = primary_ticket.status
            primary_ticket.status = Complaint.Status.IN_PROGRESS
            primary_ticket.save(update_fields=['status'])

            # توثيق حركة التذكرة الأساسية
            ComplaintHistory.objects.create(
                complaint=primary_ticket,
                action_by=user,
                old_status=old_primary_status,
                new_status=Complaint.Status.IN_PROGRESS,
                notes=f"تم دمج التذاكر التالية مع هذه التذكرة: {', '.join(tickets_to_merge_raw)}"
            )

            # ب. تحديث وإخفاء التذاكر المدمجة
            for ticket in tickets_to_merge:
                t_old_status = ticket.status
                ticket.status = Complaint.Status.CLOSED # إغلاقها/إخفاؤها
                ticket.merged_to = primary_ticket       # ربطها بالتذكرة الأساسية
                ticket.save(update_fields=['status', 'merged_to'])

                # توثيق حركة التذاكر المدمجة
                ComplaintHistory.objects.create(
                    complaint=ticket,
                    action_by=user,
                    old_status=t_old_status,
                    new_status=Complaint.Status.CLOSED,
                    notes=f"تم إغلاق التذكرة ودمجها مع التذكرة الأساسية {primary_id_raw}"
                )

        # 📤 6. إرسال الرد
        current_merged_count = primary_ticket.duplicate_tickets.count()
        
        return Response({
            "status": "success",
            "message": "تم دمج التذاكر بنجاح وتحديث حالة التذكرة الأساسية إلى قيد التنفيذ.",
            "mergedCount": current_merged_count
        }, status=status.HTTP_200_OK)

ValueError# أضف هذا الكلاس في نهاية ملف complaints/views.py

class SendTicketUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id, *args, **kwargs):
        user = request.user
        
        # 🛡️ 1. الحماية: التأكد أن المستخدم خبير صيانة أو مدير
        allowed_roles = ['tier2_liaison', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك بإرسال تحديثات. هذه الواجهة مخصصة لخبراء الصيانة.")

        # 📝 2. التحقق من صحة البيانات
        serializer = SendUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        message = serializer.validated_data['message']
        clean_ticket_id = ticket_id.replace('#', '')

        # 🔍 3. جلب التذكرة
        try:
            complaint = Complaint.objects.get(ticket_number=clean_ticket_id)
        except Complaint.DoesNotExist:
            return Response({"error": "البلاغ غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        # 🔒 حماية إضافية (اختيارية ولكن احترافية): التأكد أن التذكرة محالة لهذا الموظف تحديداً (أو أنه مدير)
        if complaint.current_assignee != user and 'super_admin' not in user_roles:
            return Response({"error": "لا يمكنك تحديث شكوى غير محالة إليك."}, status=status.HTTP_403_FORBIDDEN)

        # ⚙️ 4. تحديث التذكرة
        complaint.specialist_message = message
        # ميزة برمجية: إذا كانت حالة التذكرة "محالة"، بمجرد أن يرسل تحديث للمواطن ستتحول تلقائياً إلى "قيد التنفيذ"
        if complaint.status == Complaint.Status.ASSIGNED:
            complaint.status = Complaint.Status.IN_PROGRESS
            
        complaint.save(update_fields=['specialist_message', 'status'])

        # 📜 5. توثيق الحركة في سجل الشكوى (History)
        ComplaintHistory.objects.create(
            complaint=complaint,
            action_by=user,
            old_status=complaint.status,
            new_status=complaint.status,
            notes=f"تم إرسال تحديث للمواطن: {message}"
        )
# 🔔 6. إرسال إشعار داخلي (في قاعدة البيانات)
        Notification.objects.create(
            user=complaint.citizen,
            title=f"تحديث جديد بخصوص بلاغك #{complaint.ticket_number}",
            body=message
        )

        # 🚀 7. إرسال إشعار فايربيس (Push Notification) للهاتف
        # نمرر ticket_id لكي يفتح الفرونت إند شاشة البلاغ مباشرة (Deep Linking)
        send_push_notification(
            user=complaint.citizen,
            title=f"تحديث جديد لبلاغك #{complaint.ticket_number}",
            body=message,
            ticket_id=complaint.ticket_number
        )

        # 📤 8. إرسال الرد للفرونت إند
        return Response({
            "status": "success",
            "message": "تم إرسال التحديث للمواطن وإشعاره بنجاح."
        }, status=status.HTTP_200_OK)

# أضف هذا الكلاس في نهاية ملف complaints/views.py

class ResolveTicketView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, ticket_id, *args, **kwargs):
        user = request.user
        
        # 🛡️ 1. الحماية: التأكد أن المستخدم خبير صيانة أو مدير
        allowed_roles = ['tier2_liaison', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لخبراء الصيانة.")

        # تنظيف رقم التذكرة من رمز #
        clean_ticket_id = ticket_id.replace('#', '')

        # 🔍 2. جلب التذكرة
        try:
            complaint = Complaint.objects.get(ticket_number=clean_ticket_id)
        except Complaint.DoesNotExist:
            return Response({"error": "البلاغ غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        # 🔒 3. حماية الملكية: هل التذكرة فعلاً محالة لهذا الموظف؟
        if complaint.current_assignee != user and 'super_admin' not in user_roles:
            return Response({"error": "لا يمكنك إغلاق شكوى لم يتم إحالتها إليك."}, status=status.HTTP_403_FORBIDDEN)

        # ⚖️ 4. التحقق من الحالة المنطقية للتذكرة
        if complaint.status == Complaint.Status.RESOLVED:
            return Response({"message": "تم الإبلاغ عن حل هذه الشكوى مسبقاً."}, status=status.HTTP_200_OK)
        
        if complaint.status in [Complaint.Status.CLOSED, Complaint.Status.REJECTED]:
            return Response({"error": "لا يمكن تعديل شكوى مغلقة أو مرفوضة."}, status=status.HTTP_400_BAD_REQUEST)

        # ⚙️ 5. تحديث حالة التذكرة
        old_status = complaint.status
        complaint.status = Complaint.Status.RESOLVED
        complaint.save(update_fields=['status'])

        # 📜 6. توثيق الحركة (Audit Trail)
        ComplaintHistory.objects.create(
            complaint=complaint,
            action_by=user,
            old_status=old_status,
            new_status=Complaint.Status.RESOLVED,
            notes="قام خبير الصيانة بمعالجة المشكلة والإبلاغ عن حلها، بانتظار تقييم المواطن."
        )
# 🔔 7. إرسال الإشعار الداخلي لتطبيق المواطن
        Notification.objects.create(
            user=complaint.citizen,
            title="تم حل مشكلتك! 🥳",
            body=f"تمت معالجة البلاغ رقم #{complaint.ticket_number}. يرجى تقييم الخدمة لإغلاق البلاغ نهائياً."
        )

        # 🚀 8. رنة هاتف المواطن (Firebase Push)
        send_push_notification(
            user=complaint.citizen,
            title="تم حل مشكلتك! 🥳",
            body="فريق الصيانة أبلغنا بانتهاء العمل، نرجو منك تقييم الخدمة للحصول على نقاطك.",
            ticket_id=complaint.ticket_number
        )

        # 📤 9. إرسال الرد
        return Response({
            "status": "success",
            "message": "تم تحويل حالة البلاغ إلى (تم الحل)، وتم إرسال إشعار للمواطن."
        }, status=status.HTTP_200_OK)
class AdminDashboardStatsView(APIView):
    # لا يدخل هنا إلا المسجل دخوله (سنفحص الصلاحيات بالداخل)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # 🛡️ 1. الحماية: التأكد أن المستخدم هو مدير النظام حصراً (Super Admin)
        if not user.groups.filter(name='super_admin').exists() and not user.is_superuser:
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لمدير النظام فقط.")

        # 📊 2. جلب إجمالي التذاكر (استعلام سريع للعدد فقط)
        total_tickets = Complaint.objects.count()

        # 📈 3. حساب نسبة الإنجاز
        completed_tickets = Complaint.objects.filter(
            status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED]
        ).count()
        
        # (حماية من خطأ القسمة على صفر DivisionByZero في حال كانت قاعدة البيانات فارغة)
        completion_rate = 0
        if total_tickets > 0:
            completion_rate = int((completed_tickets / total_tickets) * 100)

        # 👥 4. حساب عدد الموظفين النشطين (مأموري الفرز + خبراء الصيانة)
        # distinct() تضمن عدم تكرار الموظف لو كان يمتلك أكثر من رتبة
        active_employees = CustomUser.objects.filter(
            groups__name__in=['tier1_dispatcher', 'tier2_liaison']
        ).distinct().count()

        # 🏢 5. تجميع التذاكر حسب التصنيف (Tickets By Category) - (GROUP BY SQL)
        categories_stats = Complaint.objects.values('category__name_ar').annotate(
            count=Count('id')
        ).order_by('-count')

        tickets_by_category = {}
        worst_sector = "غير متوفر" # قيمة افتراضية

        if categories_stats:
            # القطاع الأسوأ هو الأول في القائمة لأننا رتبناها تنازلياً (-count)
            worst_sector = categories_stats[0]['category__name_ar']
            
            # تحويل النتيجة لـ Dictionary كما يطلب الفرونت إند بالضبط
            for cat in categories_stats:
                # إذا كانت التذكرة بلا تصنيف (نظرياً لا يجب أن تحدث، لكن كودنا آمن)
                name = cat['category__name_ar'] or "أخرى"
                tickets_by_category[name] = cat['count']

        # 🗺️ 6. تجميع التذاكر حسب المحافظة (Tickets By Governorate)
        governorates_stats = Complaint.objects.values('governorate__name_ar').annotate(
            count=Count('id')
        )
        
        tickets_by_governorate = {}
        for gov in governorates_stats:
            name = gov['governorate__name_ar'] or "غير محدد"
            tickets_by_governorate[name] = gov['count']

        # 📤 7. بناء الرد النهائي ليتطابق 100% مع عقد الواجهة الأمامية (Frontend Contract)
        data = {
            "totalTickets": total_tickets,
            "completionRate": completion_rate,
            "worstSector": worst_sector,
            "activeEmployees": active_employees,
            "ticketsByGovernorate": tickets_by_governorate,
            "ticketsByCategory": tickets_by_category
        }

        return Response(data, status=status.HTTP_200_OK)

class TicketHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id, *args, **kwargs):
        user = request.user
        
        # 🛡️ 1. الحماية: السماح للموظفين والإدارة فقط (مأمور الفرز + خبير الصيانة + الإدارة)
        allowed_roles = ['tier1_dispatcher', 'tier2_liaison', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك بمشاهدة السجل الداخلي للشكوى.")

        # 🧹 2. تنظيف رقم التذكرة (إزالة # إذا أرسلها الفرونت إند)
        clean_ticket_id = ticket_id.replace('#', '')

        # 🔍 3. جلب الشكوى للتأكد من وجودها
        try:
            complaint = Complaint.objects.get(ticket_number=clean_ticket_id)
        except Complaint.DoesNotExist:
            return Response({"error": "البلاغ غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        # 🚀 4. جلب سجل الحركات (التاريخ) الخاص بهذه الشكوى
        # استخدمنا select_related لجلب بيانات منفذ الحركة بسرعة بدون إرهاق السيرفر
        history = ComplaintHistory.objects.filter(complaint=complaint)\
            .select_related('action_by')\
            .order_by('action_date') # الترتيب من الأقدم للأحدث (Timeline)

        # 📦 5. تحويل البيانات وإرسالها
        serializer = TicketHistoryTimelineSerializer(history, many=True)
        
        return Response({
            "status": "success",
            "ticket_id": f"#{complaint.ticket_number}",
            "created_at": complaint.submitted_at, # أرسلنا تاريخ الإنشاء الأساسي هنا أيضاً
            "history": serializer.data
        }, status=status.HTTP_200_OK)

class LiaisonFullArchiveView(generics.ListAPIView):
    serializer_class = LiaisonInboxSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # 🛡️ 1. الحماية: فقط خبير الصيانة (أو الإدارة) يحق له رؤية أرشيفه
        allowed_roles = ['tier2_liaison', 'super_admin']
        user_roles = [group.name for group in user.groups.all()]
        if not any(role in allowed_roles for role in user_roles):
            raise PermissionDenied("غير مصرح لك. هذه الواجهة مخصصة لخبراء الصيانة.")

        # 🚀 2. الاستعلام الذكي (O(1) Database Hit):
        # نجلب كل التذاكر التي إما:
        # أ) هو المسؤول الحالي عنها (current_assignee)
        # ب) أو قام بأي حركة عليها في السابق (موجود في تاريخ الشكوى history__action_by)
        # نستخدم distinct() لكي لا تتكرر التذكرة إذا كان قد قام بعدة حركات عليها!
        
        queryset = Complaint.objects.filter(
            Q(current_assignee=user) | Q(history__action_by=user)
        ).select_related(
            'governorate', 'category', 'citizen', 'current_assignee'
        ).prefetch_related(
            'attachments', 
            'citizen__kyc_requests', 
            'duplicate_tickets', 
            'history'
        ).distinct().order_by('-updated_at') # ترتيب من الأحدث للأقدم

        return queryset

    def list(self, request, *args, **kwargs):
        # تغليف المصفوفة داخل كائن ليكون الرد منظماً (Best Practice)
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "status": "success",
            "total_count": queryset.count(),
            "archive": serializer.data
        }, status=status.HTTP_200_OK)
class ToggleUpvoteComplaintView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_number, *args, **kwargs):
        user = request.user
        
        # 1. تنظيف رقم التذكرة (إذا أرسله الفرونت إند مع رمز #)
        clean_ticket_number = ticket_number.replace('#', '')
        
        # 2. جلب الشكوى
        try:
            complaint = Complaint.objects.get(ticket_number=clean_ticket_number)
        except Complaint.DoesNotExist:
            return Response({"error": "البلاغ غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        # 3. منع صاحب الشكوى نفسه من التأييد (لأنه من البديهي أنه متضرر) - خطوة احترافية
        if complaint.citizen == user:
            return Response(
                {"error": "لا يمكنك تأييد بلاغ قمت أنت بتقديمه."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. منطق التبديل (Toggle): إضافة أو حذف الصوت
        if complaint.upvotes.filter(id=user.id).exists():
            complaint.upvotes.remove(user)
            has_upvoted = False
        else:
            complaint.upvotes.add(user)
            has_upvoted = True
            
        # 5. جلب العدد الجديد بعد التحديث
        upvotes_count = complaint.upvotes.count()

        # 🔥 6. الميزة الذكية (الترقية إلى أولوية عاجلة)
        if upvotes_count >= 10 and not complaint.is_urgent:
            complaint.is_urgent = True
            complaint.save(update_fields=['is_urgent'])
            
            # توثيق أن النظام حولها لشكوى عاجلة تلقائياً
            ComplaintHistory.objects.create(
                complaint=complaint,
                action_by=user, # أو يمكنك جعل action_by يقبل null ليدل على أنه (النظام)
                old_status=complaint.status,
                new_status=complaint.status,
                notes="النظام الذكي: تم ترقية البلاغ إلى (أولوية عاجلة) لتجاوز عدد المتأثرين 10 أشخاص."
            )

        # إلغاء الحالة العاجلة إذا قل العدد عن 10 (إذا قام أحدهم بسحب صوته)
        elif upvotes_count < 10 and complaint.is_urgent:
            complaint.is_urgent = False
            complaint.save(update_fields=['is_urgent'])

        # 7. إرسال الرد المطابق تماماً لما طلبه الفرونت إند
        return Response({
            "upvotes_count": upvotes_count,
            "has_upvoted": has_upvoted
        }, status=status.HTTP_200_OK)
class VerifyComplaintView(APIView):
    # ⚠️ مهم جداً: هذا الـ API متاح للجميع (لأي شخص يمسح الـ QR Code)
    permission_classes = [AllowAny]

    def get(self, request, ticket_number, *args, **kwargs):
        # 1. تنظيف رقم التذكرة
        clean_ticket_number = ticket_number.replace('#', '')
        
        # 2. البحث عن الشكوى
        try:
            complaint = Complaint.objects.get(ticket_number=clean_ticket_number)
        except Complaint.DoesNotExist:
            return Response({
                "is_authentic": False,
                "error": "هذا المستند غير صالح أو مزور، رقم البلاغ غير موجود في النظام."
            }, status=status.HTTP_404_NOT_FOUND)

        # 3. إرجاع البيانات
        serializer = VerifyComplaintSerializer(complaint)
        return Response({
            "is_authentic": True,
            "message": "مستند حكومي معتمد ومسجل في النظام الذكي.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)