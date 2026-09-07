# إنشاء ملف accounts/urls.py
from django.urls import path
from .views import AdminLoginView, ChangePasswordView, CreateEmployeeView, DashboardLoginView, LoginView, RegisterView , SendOTPView, SubmitKYCView, UpdateProfileView, VerifyOTPView, ResetPasswordView


urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'), 
    path('admin-login/', AdminLoginView.as_view(), name='admin-login'),
    path('login/', DashboardLoginView.as_view(), name='dashboard-login'), 
    path('employees/create/', CreateEmployeeView.as_view(), name='create-employee'),
    path('forgot-password/send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('forgot-password/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('forgot-password/reset/', ResetPasswordView.as_view(), name='reset-password'),
    path('kyc/submit/', SubmitKYCView.as_view(), name='kyc-submit'),
    path('profile/update/', UpdateProfileView.as_view(), name='profile-update'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
]