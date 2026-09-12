from rest_framework import serializers
from django.contrib.auth.models import Group
from .models import CustomUser, KYCRequest, AuditLog, Notification
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from rest_framework.exceptions import AuthenticationFailed
import re
class RegisterSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = CustomUser
        fields = ['full_name', 'email', 'password']

    def create(self, validated_data):
        # نستخدم create_user لضمان تشفير كلمة المرور بشكل صحيح
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password']
        )
        # ملاحظة: الـ Signal الذي أنشأناه سابقاً سيقوم تلقائياً بربطه بمجموعة 'Citizen'
        return user


# 2. Serializer لعرض بيانات المستخدم
class UserSerializer(serializers.ModelSerializer):
    # حقل مخصص لجلب أدوار المستخدم (المجموعات التي ينتمي إليها)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        # لاحظ: تم حذف username و role، وتمت إضافة email و roles
        fields = ['id', 'email', 'roles', 'points', 'is_kyc_verified','managed_governorates', 'managed_categories']
        read_only_fields = ['id', 'points', 'is_kyc_verified', 'roles']

    def get_roles(self, obj):
        # إرجاع قائمة بأسماء المجموعات التي ينتمي إليها هذا المستخدم
        return [group.name for group in obj.groups.all()]


# 3. Serializer لطلبات التوثيق KYC
class KYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCRequest
        fields = '__all__'
        read_only_fields = ['status', 'reviewer', 'submitted_at']


# 4. Serializer للسجل الأمني
class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'
        read_only_fields = ['admin', 'action_time']
# أضف هذا الكلاس في أسفل الملف
class CustomLoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # هذه الدالة تقوم بالتحقق من الإيميل والباسورد تلقائياً
        data = super().validate(attrs)
        
        # إضافة بيانات المستخدم المخصصة في الرد (Response) للواجهة الأمامية
        data['user'] = {
            'id': str(self.user.id),
            'email': self.user.email,
            'full_name': getattr(self.user, 'full_name', ''),
            'is_kyc_verified': self.user.is_kyc_verified,
            'roles': [group.name for group in self.user.groups.all()]
        }
        return data
    
class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "كلمتا المرور غير متطابقتين."})
        return attrs

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        # جلبنا الحقول بنفس الأسماء التي طلبها توني في ملف الـ JSON
        fields = ['id', 'title', 'body', 'is_read', 'created_at']

class SubmitKYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCRequest
        # نطلب من الواجهة هذه الحقول الثلاثة فقط
        fields = ['national_id', 'front_id_image', 'back_id_image']

    def validate_national_id(self, value):
        # التحقق من أن الرقم الوطني يتكون من 11 رقماً وأنه أرقام فقط
        if not value.isdigit() or len(value) != 11:
            raise serializers.ValidationError("الرقم الوطني يجب أن يتكون من 11 رقماً.")
        return value

# 1. Serializer لتحديث الاسم
class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['full_name']

# 2. Serializer لتغيير كلمة المرور
class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    # validate_password هي دالة جانغو الافتراضية للتحقق من قوة الكلمة وقد قمت أنت باستدعائها مسبقاً في هذا الملف
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        # التحقق من أن كلمة المرور القديمة مطابقة
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("كلمة المرور القديمة غير صحيحة.")
        return value

class AdminLoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # 1. جلب جميع أسماء المجموعات (الرتب) التي يمتلكها هذا المستخدم
        user_groups = [group.name for group in self.user.groups.all()]
        
        # 2. تحديد الرتب المسموح لها بالدخول من هذه الواجهة (موظفين + إدارة)
        allowed_roles = ['tier1_dispatcher', 'tier2_liaison', 'super_admin']
        
        # 3. 🛡️ التحقق: هل يمتلك المستخدم أي رتبة من الرتب المسموحة؟
        has_access = any(role in allowed_roles for role in user_groups)
        
        if not has_access:
            # إذا كان مواطناً عادياً أو ليس لديه رتبة، يتم طرده
            raise AuthenticationFailed("غير مصرح لك. هذه الواجهة مخصصة للموظفين والإدارة فقط.")
        
        # 4. تحديد الرتبة الأساسية لإرسالها للفرونت إند
        # (نبحث عن أول رتبة تتطابق مع الرتب المسموحة لكي لا نرسل "citizen" بالخطأ لو كان يمتلك رتبتين)
        primary_role = next((role for role in user_groups if role in allowed_roles), "citizen")

        # 5. بناء الرد بالشكل الذي طلبه توني حرفياً
        custom_data = {
            "token": data["access"],
            "user": {
                "id": str(self.user.id),
                "name": getattr(self.user, 'full_name', ''),
                "role": primary_role # سيرسل tier1_dispatcher أو tier2_liaison أو super_admin
            }
        }
        
        return custom_data



class DashboardLoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # 1. التحقق من صحة الإيميل والباسورد
        data = super().validate(attrs)
        
        # 2. جلب جميع المجموعات (الرتب) التي يمتلكها المستخدم
        user_groups = [group.name for group in self.user.groups.all()]
        
        # 3. تحديد الرتب المسموحة للويب داشبورد (كما طلب الفرونت إند بالضبط)
        allowed_roles = ['tier1_dispatcher', 'tier2_liaison', 'super_admin']
        
        # 4. البحث عن الرتبة المطابقة للمستخدم
        # سيأخذ رتبته المسموحة، وإذا لم يكن لديه أي منها سيصبح None
        primary_role = next((role for role in user_groups if role in allowed_roles), None)
        
        # 5. 🛡️ الحماية الصارمة: إذا كان مواطناً (citizen) أو رتبته غير مدعومة، يتم طرده
        if not primary_role:
            raise AuthenticationFailed("غير مصرح لك بالدخول. هذه الواجهة مخصصة للإدارة والموظفين فقط.")

        # 6. بناء الرد النهائي ليتطابق 100% مع طلب الفرونت إند
        return {
            "token": data["access"],
            "user": {
                "id": str(self.user.id),
                "name": getattr(self.user, 'full_name', ''),
                "role": primary_role  # سيُرجع حصراً واحدة من الرتب الثلاثة
            }
        }

class CreateEmployeeSerializer(serializers.ModelSerializer):
    # نطلب الرتبة من الفرونت إند
    role = serializers.ChoiceField(choices=['tier1_dispatcher', 'tier2_liaison'], write_only=True)
    # الفرونت إند عادة يرسل "name" بدلاً من "full_name"
    name = serializers.CharField(source='full_name')
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = CustomUser
        fields = ['email', 'password', 'name', 'role']

    def create(self, validated_data):
        # 1. استخراج الرتبة من البيانات
        role = validated_data.pop('role')
        
        # 2. إنشاء المستخدم وتشفير كلمة المرور تلقائياً
        user = CustomUser.objects.create_user(**validated_data)
        
        # 3. إزالة رتبة "مواطن" الافتراضية (التي يضيفها الـ Signal تلقائياً)
        user.groups.clear()
        
        # 4. تعيين الرتبة الجديدة (مأمور فرز أو خبير صيانة)
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
        
        return user
class PendingKYCSerializer(serializers.ModelSerializer):
    # الحقول المخصصة لتطابق طلب الفرونت إند
    id = serializers.SerializerMethodField()
    nationalId = serializers.CharField(source='national_id')
    fullName = serializers.CharField(source='citizen.full_name')
    dateSubmitted = serializers.DateTimeField(source='submitted_at')
    frontPhoto = serializers.ImageField(source='front_id_image')
    backPhoto = serializers.ImageField(source='back_id_image')

    class Meta:
        model = KYCRequest
        fields = ['id', 'nationalId', 'fullName', 'dateSubmitted', 'frontPhoto', 'backPhoto']

    def get_id(self, obj):
        # إضافة البادئة "kyc-" كما طلب الفرونت إند بالضبط
        return f"kyc-{obj.id}"

class RejectKYCSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=True,
        error_messages={
            'required': 'سبب الرفض مطلوب.',
            'blank': 'لا يمكن أن يكون سبب الرفض فارغاً.'
        }
    )
class BreakGlassSerializer(serializers.Serializer):
    targetTicketId = serializers.CharField(
        required=True, 
        error_messages={'required': 'رقم التذكرة مطلوب.'}
    )
    reason = serializers.CharField(
        required=True, 
        error_messages={'required': 'سبب كشف الهوية (التفويض) مطلوب لتسجيله في النظام.'}
    )
class BreakGlassLogSerializer(serializers.ModelSerializer):
    # تنسيق الحقول لتطابق الفرونت إند تماماً
    id = serializers.SerializerMethodField()
    timestamp = serializers.DateTimeField(source='action_time')
    adminName = serializers.CharField(source='admin.full_name', default="مدير غير معروف")
    targetTicketId = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'timestamp', 'adminName', 'targetTicketId', 'reason']

    def get_id(self, obj):
        # إضافة البادئة aud-
        return f"aud-{obj.id}"

    def get_targetTicketId(self, obj):
        # استخراج رقم التذكرة الذي يبدأ بـ #CMT- من داخل النص باستخدام Regex
        match = re.search(r'رقم (#CMT-\d+)', obj.details)
        return match.group(1) if match else "غير متوفر"

    def get_reason(self, obj):
        # استخراج ما بعد كلمة "السبب المدخل:"
        match = re.search(r'السبب المدخل:\s*(.+)$', obj.details)
        return match.group(1) if match else obj.details
class FCMTokenSerializer(serializers.Serializer):
    fcm_token = serializers.CharField(required=True)
    device_type = serializers.ChoiceField(choices=['android', 'ios', 'web'], required=True)