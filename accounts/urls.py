# إنشاء ملف accounts/urls.py
from django.urls import path
from .views import AdminLoginView, ChangePasswordView, ClaimRewardView, CreateEmployeeView, DashboardLoginView, LoginView, LogoutView, RegisterView , SendOTPView, SubmitKYCView, UpdateFCMTokenView, UpdateProfileView, VerifyOTPView, ResetPasswordView


urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'), 
    path('logout/', LogoutView.as_view(), name='logout'), # 👈 الرابط الجديد
    path('admin-login/', AdminLoginView.as_view(), name='admin-login'),
    path('login/', DashboardLoginView.as_view(), name='dashboard-login'), 
    path('employees/create/', CreateEmployeeView.as_view(), name='create-employee'),
    path('forgot-password/send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('forgot-password/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('forgot-password/reset/', ResetPasswordView.as_view(), name='reset-password'),
    path('kyc/submit/', SubmitKYCView.as_view(), name='kyc-submit'),
    path('profile/update/', UpdateProfileView.as_view(), name='profile-update'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('update-fcm-token/', UpdateFCMTokenView.as_view(), name='update-fcm-token'),
    path('rewards/claim/', ClaimRewardView.as_view(), name='claim-reward'),
]