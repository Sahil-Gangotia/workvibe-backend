"""
URL configuration for Backend project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

def home_view(request):
    return HttpResponse("Welcome to the WorkVibe Backend API is running successfully!")

urlpatterns = [
    path('', home_view),  # <-- Fixes the root URL 404 error
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    
    # JWT Authentication Endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),       # Login Endpoint
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), # Refresh Token Endpoint
]

# Serve uploaded files (Resumes, Logos) during local development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)