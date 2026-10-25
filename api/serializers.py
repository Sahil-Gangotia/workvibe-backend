from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Job, Company, Application

User = get_user_model()

# 1. Company Serializer
class CompanySerializer(serializers.ModelSerializer):
    job_count = serializers.IntegerField(source='jobs.count', read_only=True)

    class Meta:
        model = Company
        fields = '__all__'


# 2. Job Serializer
class JobSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(write_only=True)
    company = CompanySerializer(read_only=True)

    class Meta:
        model = Job
        fields = ['id', 'title', 'company_name', 'company', 'location', 'job_type', 'salary', 'description', 'posted_at']

    def create(self, validated_data):
        company_name = validated_data.pop('company_name')
        
        company_obj, created = Company.objects.get_or_create(
            name=company_name,
            defaults={
                'industry': 'Technology',
                'location': validated_data.get('location', 'Remote'),
                'description': 'Auto-created via Job Portal'
            }
        )
        
        job = Job.objects.create(company=company_obj, **validated_data)
        return job


# 3. Application Serializer (Job Apply, Status Update & Resume Upload)
class ApplicationSerializer(serializers.ModelSerializer):
    job_title = serializers.CharField(source='job.title', read_only=True)
    company_name = serializers.CharField(source='job.company.name', read_only=True)
    applicant_username = serializers.CharField(source='applicant.username', read_only=True)
    
    # Status field explicit definition to ensure PATCH requests accept exact strings
    status = serializers.CharField(required=False, default='Pending')

    class Meta:
        model = Application
        fields = [
            'id', 
            'job', 
            'job_title', 
            'company_name', 
            'applicant', 
            'applicant_username',
            'full_name', 
            'email', 
            'phone', 
            'resume', 
            'cover_letter', 
            'status', 
            'applied_at'
        ]
        read_only_fields = ['applicant', 'applied_at']


# 4. User Registration Serializer
class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    role = serializers.CharField(required=False, default='candidate')
    company_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'role', 'company_name']

    def create(self, validated_data):
        company_name = validated_data.pop('company_name', '')
        user_role = str(validated_data.pop('role', 'candidate')).lower().strip()

        # Base User account create karna
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', '')
        )

        # Role Explicit Assignment
        setattr(user, 'role', user_role)
        user.role = user_role
        user.save()

        # Recruiter registration par Company auto-create
        if user_role == 'recruiter' and company_name:
            Company.objects.get_or_create(
                name=company_name,
                defaults={
                    'industry': 'Technology',
                    'description': f'Auto-created for recruiter {user.username}'
                }
            )

        return user


# 5. Custom JWT Login Token Serializer
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # JWT access token claims ke andar role safely inject karna
        user_role = str(getattr(user, 'role', 'candidate') or 'candidate').lower().strip()
        token['role'] = user_role
        token['username'] = user.username
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user_role = str(getattr(self.user, 'role', 'candidate') or 'candidate').lower().strip()
        
        data['role'] = user_role
        data['user_role'] = user_role
        data['username'] = self.user.username
        data['email'] = self.user.email
        return data