import os

from rest_framework import serializers

from .models import Governorate, Category, Complaint, Attachment,ComplaintHistory

class GovernorateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Governorate
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = '__all__'
        read_only_fields = ['uploaded_at']

class ComplaintHistorySerializer(serializers.ModelSerializer):
    # جلب إيميل المنفذ والمحال إليه لتسهيل العرض في الواجهة
    action_by_email = serializers.ReadOnlyField(source='action_by.email')
    assigned_to_email = serializers.ReadOnlyField(source='assigned_to.email')

    class Meta:
        model = ComplaintHistory
        fields = '__all__'
        read_only_fields = ['id', 'action_date']

class ComplaintSerializer(serializers.ModelSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)
    history = ComplaintHistorySerializer(many=True, read_only=True)
    class Meta:
        model = Complaint
        fields = '__all__'
        read_only_fields = ['id', 'status', 'merged_to', 'submitted_at', 'updated_at', 'citizen_rating', 'current_assignee']
class CreateComplaintSerializer(serializers.ModelSerializer):
    # سنستقبل التصنيف كنص كما طلب توني، وسنعالجه في الـ View
    category_name = serializers.CharField(write_only=True)
    
    class Meta:
        model = Complaint
        fields = ['title', 'description', 'location', 'category_name','latitude', 'longitude','audio_file']
    def validate_audio_file(self, value):
        if value:
            ext = os.path.splitext(value.name)[1].lower()
            valid_extensions = ['.mp3', '.m4a']
            if ext not in valid_extensions:
                raise serializers.ValidationError(f"صيغة الملف غير مدعومة. يرجى رفع ملف بصيغة {valid_extensions}")
        return value
class ComplaintListSerializer(serializers.ModelSerializer):
    # تغيير أسماء الحقول لتطابق ما طلبه مطور الفرونت إند بالضبط
    ticket_id = serializers.ReadOnlyField(source='ticket_number')
    category = serializers.ReadOnlyField(source='category.name_ar') # نرسل اسم التصنيف بالعربي
    
    # فصل التاريخ والوقت وتنسيقهما
    created_at = serializers.DateTimeField(format="%Y-%m-%d", source='submitted_at')
    time = serializers.DateTimeField(format="%H:%M", source='submitted_at')

    class Meta:
        model = Complaint
        fields = ['ticket_id', 'title', 'category', 'status', 'created_at', 'time']



class ComplaintDetailSerializer(serializers.ModelSerializer):
    ticket_id = serializers.ReadOnlyField(source='ticket_number')
    # توني استخدم في الـ JSON كلمة "water"، لذا سنرسل له الاسم الإنجليزي للتصنيف (أو يمكنك تغييرها لـ name_ar لو أردت العربي)
    category = serializers.ReadOnlyField(source='category.name_en') 
    created_at = serializers.DateTimeField(source='submitted_at')
    
    # حقل مخصص لكي نعرف هل التذكرة تم تقييمها أم لا
    is_evaluated = serializers.SerializerMethodField()
    audio_file_url = serializers.FileField(source='audio_file', read_only=True) 
    upvotes_count = serializers.SerializerMethodField()
    has_upvoted = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True, read_only=True)
    class Meta:
        model = Complaint
        fields = [
            'ticket_id', 'title', 'description', 'location', 
            'category', 'status', 'created_at', 
            'specialist_message', 'is_evaluated','latitude', 'longitude','audio_file_url'
            ,'upvotes_count', 'has_upvoted','attachments'
        ]
        

    def get_is_evaluated(self, obj):
        # ترجع True إذا كان حقل التقييم يحتوي على داتا، و False إذا كان فارغاً
        return bool(obj.citizen_rating)
    def get_upvotes_count(self, obj):
        return obj.upvotes.count() # يجلب إجمالي عدد المصوتين

    def get_has_upvoted(self, obj):
        # التحقق مما إذا كان المستخدم الذي طلب الـ API موجوداً ضمن المصوتين
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.upvotes.filter(id=request.user.id).exists()
        return False

class EvaluateComplaintSerializer(serializers.Serializer):
    is_fixed = serializers.BooleanField(required=True)
class Tier1NewTicketSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    governorate = serializers.CharField(source='governorate.name_ar', default='غير محدد')
    category = serializers.CharField(source='category.name_ar', default='غير محدد')
    date = serializers.DateTimeField(source='submitted_at')
    citizenName = serializers.CharField(source='citizen.full_name', default='غير معروف')
    citizenId = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    isReopened = serializers.SerializerMethodField()
    audio_file_url = serializers.FileField(source='audio_file', read_only=True) 
    class Meta:
        model = Complaint
        fields = [
            'id', 'governorate', 'category', 'description', 
            'date', 'status', 'citizenName', 'citizenId', 
            'media', 'isReopened','latitude', 'longitude', 'audio_file_url'
        ]

    def get_id(self, obj):
        # إضافة رمز الشباك كما طلب الفرونت إند
        return f"#{obj.ticket_number}"

    def get_citizenId(self, obj):
        # البحث عن الرقم الوطني للمواطن من طلبات التوثيق (KYC)
        kyc = obj.citizen.kyc_requests.filter(status='approved').first()
        if not kyc:
            kyc = obj.citizen.kyc_requests.last() # إذا لم يعتمد بعد، نجلب أحدث طلب
            
        return kyc.national_id if kyc else "غير متوفر"

    def get_media(self, obj):
        # فحص المرفقات لمعرفة نوعها
        attachments = obj.attachments.all()
        if not attachments:
            return "none"
        
        # إذا كان هناك مرفقات، نفحص نوعها
        for att in attachments:
            if 'image' in att.file_type.lower():
                return "photo"
            if 'audio' in att.file_type.lower() or 'voice' in att.file_type.lower():
                return "voice"
        return "photo" # كقيمة افتراضية إذا لم يتم التعرف على النوع

    def get_isReopened(self, obj):
        # التذكرة تعتبر معادة إذا كان في تاريخها حالة سابقة (كانت محلولة ثم رجعت)
        # للشكاوى الجديدة ستكون دائماً False
        return obj.history.filter(new_status='newStatus').count() > 1
class DispatcherNewTicketSerializer(serializers.ModelSerializer):
    # استخدام SerializerMethodField للحقول التي تحتاج منطق برمجي مخصص
    id = serializers.SerializerMethodField()
    governorate = serializers.CharField(source='governorate.name_ar', default='غير محدد')
    category = serializers.CharField(source='category.name_ar', default='غير محدد')
    date = serializers.DateTimeField(source='submitted_at')
    citizenName = serializers.CharField(source='citizen.full_name', default='غير معروف')
    citizenId = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    isReopened = serializers.SerializerMethodField()
    audio_file_url = serializers.FileField(source='audio_file', read_only=True)
    class Meta:
        model = Complaint
        fields = [
            'id', 'governorate', 'category', 'description', 
            'date', 'status', 'citizenName', 'citizenId', 
            'media', 'isReopened', 'latitude', 'longitude','audio_file_url'
        ]

    def get_id(self, obj):
        # إضافة رمز # كما طلب الفرونت إند
        return f"#{obj.ticket_number}"

    def get_citizenId(self, obj):
        # جلب الرقم الوطني من أول طلب KYC (يفضل أن يكون المقبول)
        # استخدمنا all() هنا بدلاً من filter() لكي نستفيد من prefetch_related في الـ View
        kyc_requests = obj.citizen.kyc_requests.all()
        for kyc in kyc_requests:
            if kyc.status == 'approved':
                return kyc.national_id
        # إذا لم يوجد طلب مقبول، نرجع أول طلب موجود أو "غير متوفر"
        if kyc_requests:
            return kyc_requests[0].national_id
        return "غير متوفر"

    def get_media(self, obj):
        # فحص المرفقات بدون ضرب قاعدة البيانات مراراً (بفضل prefetch_related)
        attachments = obj.attachments.all()
        if not attachments:
            return "none"
        
        # إذا كان هناك مقطع صوتي نرجع voice، غير ذلك نرجع photo
        for att in attachments:
            if 'audio' in att.file_type.lower() or 'voice' in att.file_type.lower():
                return "voice"
        return "photo"
    def get_isReopened(self, obj):
        # تذكرة جديدة يعني لم تفتح من قبل
         pass
         return False
    # تأكد من وضع هذا الكود في آخر ملف complaints/serializers.py

class LiaisonInboxSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    governorate = serializers.CharField(source='governorate.name_ar', default='غير محدد')
    category = serializers.CharField(source='category.name_ar', default='غير محدد')
    date = serializers.DateTimeField(source='submitted_at')
    assignedTo = serializers.CharField(source='current_assignee.full_name', default='غير محدد')
    citizenName = serializers.CharField(source='citizen.full_name', default='غير معروف')
    citizenId = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    mergedCount = serializers.SerializerMethodField()
    isReopened = serializers.SerializerMethodField()
    citizenFeedback = serializers.SerializerMethodField()
    audio_file_url = serializers.FileField(source='audio_file', read_only=True)

    class Meta:
        model = Complaint
        fields = [
            'id', 'governorate', 'category', 'description', 
            'date', 'status', 'assignedTo', 'citizenName', 
            'citizenId', 'media', 'mergedCount', 
            'isReopened', 'citizenFeedback','latitude', 'longitude', 'audio_file_url'
        ]

    def get_id(self, obj):
        return f"#{obj.ticket_number}"

    def get_citizenId(self, obj):
        kyc_requests = obj.citizen.kyc_requests.all()
        for kyc in kyc_requests:
            if kyc.status == 'approved':
                return kyc.national_id
        if kyc_requests:
            return kyc_requests[0].national_id
        return "غير متوفر"

    def get_media(self, obj):
        attachments = obj.attachments.all()
        if not attachments:
            return "none"
        for att in attachments:
            if 'audio' in att.file_type.lower() or 'voice' in att.file_type.lower():
                return "voice"
        return "photo"

    def get_mergedCount(self, obj):
        return obj.duplicate_tickets.count()

    def get_isReopened(self, obj):
        from .models import RatingChoices
        return obj.citizen_rating == RatingChoices.UNSATISFIED

    def get_citizenFeedback(self, obj):
        if not self.get_isReopened(obj):
            return None
        last_history = obj.history.filter(action_by=obj.citizen).first()
        if last_history and last_history.notes:
            return last_history.notes
        return "المواطن غير راضٍ عن الحل المقدم وطلب إعادة فتح الشكوى."
# أضف هذا في نهاية ملف complaints/serializers.py

class MergeTicketsSerializer(serializers.Serializer):
    primaryTicketId = serializers.CharField(
        required=True, 
        error_messages={'required': 'رقم التذكرة الأساسية مطلوب.'}
    )
    ticketIdsToMerge = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=False, # لا نقبل مصفوفة فارغة
        error_messages={
            'required': 'يجب إرسال مصفوفة التذاكر المراد دمجها.',
            'empty': 'مصفوفة التذاكر يجب أن تحتوي على تذكرة واحدة على الأقل.'
        }
    )

# أضف هذا الكلاس في نهاية ملف complaints/serializers.py

class SendUpdateSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True, 
        error_messages={
            'required': 'نص الرسالة مطلوب.',
            'blank': 'لا يمكن إرسال رسالة فارغة.'
        }
    )
class TicketHistoryTimelineSerializer(serializers.ModelSerializer):
    actorName = serializers.CharField(source='action_by.full_name', default="غير معروف")
    actorRole = serializers.SerializerMethodField()
    timestamp = serializers.DateTimeField(source='action_date')
    
    class Meta:
        model = ComplaintHistory
        fields = ['id', 'actorName', 'actorRole', 'old_status', 'new_status', 'notes', 'timestamp']

    def get_actorRole(self, obj):
        # تحديد رتبة الشخص الذي قام بالإجراء لتظهر بشكل جميل في الـ Timeline
        user = obj.action_by
        if user.is_superuser or user.groups.filter(name='super_admin').exists():
            return "مدير النظام"
        elif user.groups.filter(name='tier1_dispatcher').exists():
            return "مأمور الفرز"
        elif user.groups.filter(name='tier2_liaison').exists():
            return "خبير الصيانة"
        return "المواطن"
class VerifyComplaintSerializer(serializers.ModelSerializer):
    # نرجع الأسماء بالعربي لتكون واضحة في صفحة التحقق
    category = serializers.ReadOnlyField(source='category.name_ar')
    governorate = serializers.ReadOnlyField(source='governorate.name_ar')
    submitted_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Complaint
        # نرجع الحقول العامة فقط (بدون صور الهوية، وبدون اسم المواطن لحماية الخصوصية إذا أردت)
        fields = ['ticket_number', 'title', 'status', 'category', 'governorate', 'submitted_at', 'is_urgent']