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
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'roles', 'points', 'is_kyc_verified','managed_governorates', 'managed_categories']
        read_only_fields = ['id', 'points', 'is_kyc_verified', 'roles']

    def get_roles(self, obj):
        return [group.name for group in obj.groups.all()]


class KYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCRequest
        fields = '__all__'
        read_only_fields = ['status', 'reviewer', 'submitted_at']


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'
        read_only_fields = ['admin', 'action_time']
class CustomLoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
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
        fields = ['id', 'title', 'body', 'is_read', 'created_at']

class SubmitKYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCRequest
        fields = ['national_id', 'front_id_image', 'back_id_image']

    def validate_national_id(self, value):
        if not value.isdigit() or len(value) != 11:
            raise serializers.ValidationError("الرقم الوطني يجب أن يتكون من 11 رقماً.")
        return value

class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['full_name']

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("كلمة المرور القديمة غير صحيحة.")
        return value

class AdminLoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        user_groups = [group.name for group in self.user.groups.all()]
        
        allowed_roles = ['tier1_dispatcher', 'tier2_liaison', 'super_admin']
        
        has_access = any(role in allowed_roles for role in user_groups)
        
        if not has_access:
            raise AuthenticationFailed("غير مصرح لك. هذه الواجهة مخصصة للموظفين والإدارة فقط.")
        
        primary_role = next((role for role in user_groups if role in allowed_roles), "citizen")

        custom_data = {
            "token": data["access"],
            "user": {
                "id": str(self.user.id),
                "name": getattr(self.user, 'full_name', ''),
                "role": primary_role 
            }
        }
        
        return custom_data



class DashboardLoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        user_groups = [group.name for group in self.user.groups.all()]
        
        allowed_roles = ['tier1_dispatcher', 'tier2_liaison', 'super_admin']
        
        primary_role = next((role for role in user_groups if role in allowed_roles), None)
        
        if not primary_role:
            raise AuthenticationFailed("غير مصرح لك بالدخول. هذه الواجهة مخصصة للإدارة والموظفين فقط.")

        return {
            "token": data["access"],
            "user": {
                "id": str(self.user.id),
                "name": getattr(self.user, 'full_name', ''),
                "role": primary_role 
            }
        }

class CreateEmployeeSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=['tier1_dispatcher', 'tier2_liaison'], write_only=True)
    name = serializers.CharField(source='full_name')
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = CustomUser
        fields = ['email', 'password', 'name', 'role']

    def create(self, validated_data):
        role = validated_data.pop('role')
        
        user = CustomUser.objects.create_user(**validated_data)
        
        user.groups.clear()
        
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
        
        return user
class PendingKYCSerializer(serializers.ModelSerializer):
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
    id = serializers.SerializerMethodField()
    timestamp = serializers.DateTimeField(source='action_time')
    adminName = serializers.CharField(source='admin.full_name', default="مدير غير معروف")
    targetTicketId = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'timestamp', 'adminName', 'targetTicketId', 'reason']

    def get_id(self, obj):
        return f"aud-{obj.id}"

    def get_targetTicketId(self, obj):
        match = re.search(r'رقم (#CMT-\d+)', obj.details)
        return match.group(1) if match else "غير متوفر"

    def get_reason(self, obj):
        match = re.search(r'السبب المدخل:\s*(.+)$', obj.details)
        return match.group(1) if match else obj.details
class FCMTokenSerializer(serializers.Serializer):
    fcm_token = serializers.CharField(required=True)
    device_type = serializers.ChoiceField(choices=['android', 'ios', 'web'], required=True)