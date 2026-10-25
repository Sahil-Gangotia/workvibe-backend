import random
from django.core.mail import send_mail
from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.auth import authenticate, get_user_model

from .models import Job, Company, Application
from .serializers import (
    JobSerializer, 
    CompanySerializer, 
    UserRegisterSerializer,
    CustomTokenObtainPairSerializer,
    ApplicationSerializer
)

User = get_user_model()

OTP_STORAGE = {}


def get_tokens_for_user(user):
    """
    User ke liye Auth Token aur SimpleJWT Tokens dono prepare karta hai,
    role ko strictly lowercase format mein inject karta hai.
    """
    token, _ = Token.objects.get_or_create(user=user)
    refresh = RefreshToken.for_user(user)
    
    # User role safely derive & normalize karo
    user_role = str(getattr(user, 'role', 'candidate') or 'candidate').lower().strip()

    # Custom claims in JWT access token
    refresh['role'] = user_role
    refresh['user_role'] = user_role
    refresh['username'] = user.username

    return {
        'token': str(refresh.access_token), 
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'auth_token': token.key,            
        'role': user_role,
        'user_role': user_role,
        'username': user.username,
        'email': user.email
    }


# --- Custom Permission for Recruiters ---
class IsRecruiterOrReadOnly(permissions.BasePermission):
    """
    GET requests allow all users.
    POST/PUT/DELETE requires Authenticated User (strictly Recruiter, Admin, or Superuser).
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:  # GET, HEAD, OPTIONS
            return True
            
        if not (request.user and request.user.is_authenticated):
            return False

        user_role = str(getattr(request.user, 'role', '') or '').lower().strip()
        return (
            user_role in ['recruiter', 'admin'] or 
            request.user.is_staff or 
            request.user.is_superuser
        )


class IsRecruiterUser(permissions.BasePermission):
    """
    Strict permission check for Recruiter/Admin access.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        user_role = str(getattr(request.user, 'role', '') or '').lower().strip()
        return (
            user_role in ['recruiter', 'admin'] or 
            request.user.is_staff or 
            request.user.is_superuser
        )




# 1. Job ViewSet (Interview ke liye 100% Safe & AllowAny)
class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all().order_by('-posted_at')
    serializer_class = JobSerializer
    permission_classes = [permissions.AllowAny]  # Demo ke liye sabhi requests allow karega

    def perform_create(self, serializer):
        serializer.save()


# 2. Company ViewSet
class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [IsRecruiterOrReadOnly]


# 3. Application ViewSet (Handles Resume Upload, Status Update & Role-based Viewing)
class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all().order_by('-applied_at')
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    # Enabled JSONParser for status PATCH updates alongside MultiPart/FormParser
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def perform_create(self, serializer):
        serializer.save(applicant=self.request.user)

    def get_queryset(self):
        user = self.request.user
        
        if not user.is_authenticated:
            return Application.objects.none()

        user_role = str(getattr(user, 'role', '') or '').lower().strip()

        # Recruiter, Admin, Staff ya Superuser sabhi applications dekh aur update kar sakte hain
        if user_role in ['recruiter', 'admin'] or user.is_staff or user.is_superuser:
            return Application.objects.all().order_by('-applied_at')

        # Candidate ko sirf apni apply ki hui jobs dikhenge
        return Application.objects.filter(applicant=user).order_by('-applied_at')

    # Explicit Partial Update for Status Patch (Accept / Reject) - Restricted to Recruiters
    def partial_update(self, request, *args, **kwargs):
        user = request.user
        user_role = str(getattr(user, 'role', '') or '').lower().strip()
        
        if user_role not in ['recruiter', 'admin'] and not user.is_staff and not user.is_superuser:
            return Response(
                {"detail": "Only recruiters can update application status."}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        kwargs['partial'] = True
        return super().update(request, *args, **kwargs)


# 4. User Registration View
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        auth_data = get_tokens_for_user(user)
        auth_data['message'] = 'Account created successfully!'

        return Response(auth_data, status=status.HTTP_201_CREATED)


# 5. Standard Credentials Login View
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email_or_username = request.data.get('email') or request.data.get('username')
        password = request.data.get('password')

        if not email_or_username or not password:
            return Response({'error': 'Email/Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Authenticate via username
        user = authenticate(username=email_or_username, password=password)

        # 2. Fallback to Email authentication
        if not user:
            try:
                user_obj = User.objects.get(email=email_or_username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if user:
            auth_data = get_tokens_for_user(user)
            return Response(auth_data, status=status.HTTP_200_OK)
        
        return Response({'error': 'Invalid credentials. Please check email and password.'}, status=status.HTTP_401_UNAUTHORIZED)


# 6. Send Real Email OTP View (Handles Username / Email Inputs automatically)
class SendOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        input_identifier = request.data.get('email') or request.data.get('username')
        if not input_identifier:
            return Response({'error': 'Email or Username is required'}, status=status.HTTP_400_BAD_REQUEST)

        target_email = input_identifier

        # Agar input email ID nahi balki username h, to User DB se lookup karo
        if '@' not in input_identifier:
            user = User.objects.filter(username=input_identifier).first()
            if user and user.email:
                target_email = user.email
            elif not user:
                return Response({'error': f'User "{input_identifier}" not found.'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': f'No valid email registered for user "{input_identifier}".'}, status=status.HTTP_400_BAD_REQUEST)

        # Generate 6-Digit Random OTP
        otp = str(random.randint(100000, 999999))
        
        # Save OTP against both key variations
        OTP_STORAGE[input_identifier] = otp
        OTP_STORAGE[target_email] = otp

        try:
            send_mail(
                subject='WorkVibe - Your Login Verification OTP',
                message=f'Hello,\n\nYour WorkVibe verification OTP is: {otp}\n\nDo not share this OTP with anyone.',
                from_email=None,  # Uses DEFAULT_FROM_EMAIL from settings.py
                recipient_list=[target_email],
                fail_silently=False,
            )
            print(f"DEBUG: Real OTP {otp} sent successfully to {target_email}")
            return Response({'message': f'Real OTP sent successfully to {target_email}! Check your inbox/spam.'}, status=status.HTTP_200_OK)
        except Exception as e:
            print("GMAIL SMTP ERROR:", str(e))
            return Response({
                'error': f'Email sending failed: {str(e)}. Please check Gmail App Password in settings.py.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 7. Verify Real Email OTP View (Supports both Email and Username key lookups)
class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        input_identifier = request.data.get('email') or request.data.get('username')
        otp = request.data.get('otp')

        if not input_identifier or not otp:
            return Response({'error': 'Email/Username and OTP are required'}, status=status.HTTP_400_BAD_REQUEST)

        saved_otp = OTP_STORAGE.get(input_identifier)

        # Fallback to email resolution if username passed during verification
        if not saved_otp and '@' not in input_identifier:
            user_obj = User.objects.filter(username=input_identifier).first()
            if user_obj and user_obj.email:
                saved_otp = OTP_STORAGE.get(user_obj.email)

        if saved_otp and str(otp).strip() == str(saved_otp):
            # Clean up memory storage
            OTP_STORAGE.pop(input_identifier, None)

            user = User.objects.filter(email=input_identifier).first() or User.objects.filter(username=input_identifier).first()
            if user:
                auth_data = get_tokens_for_user(user)
                auth_data['message'] = 'OTP Verified Successfully!'
                return Response(auth_data, status=status.HTTP_200_OK)
                
            return Response({'error': 'User account not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'error': 'Invalid OTP! Please check the code received in your email.'}, status=status.HTTP_400_BAD_REQUEST)


# 8. Custom JWT Token Login View
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer