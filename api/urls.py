from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    JobViewSet, 
    CompanyViewSet, 
    ApplicationViewSet,
    RegisterView, 
    LoginView, 
    SendOTPView, 
    VerifyOTPView
)

router = DefaultRouter()
router.register(r'jobs', JobViewSet, basename='job')
router.register(r'companies', CompanyViewSet, basename='company')
router.register(r'applications', ApplicationViewSet, basename='application')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
]