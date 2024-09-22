from rest_framework import viewsets, status
from rest_framework.response import Response
from django.db.models import Q, F
from .models import User, BlacklistedToken
from .serializers import UserSerializer,UserLoginSerializer,UserLogoutSerializer,RefreshTokenSerializer
from core.ResponseStatus import ResponseStatus
import logging
from django.utils import timezone
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from .permission import IsAuthenticatedUser
from rest_framework import permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger("user")

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = 'id'
    permission_classes = [IsAuthenticatedUser]

    def get_permissions(self):
        if self.action == 'create':
            # Allow anyone to create a user
            return [permissions.AllowAny()]
        return super().get_permissions()
         
    def create(self, request, *args, **kwargs):
        try:
            required_fields = ['email', 'password', 'username', 'user_type']
            missing_fields = [field for field in required_fields if field not in request.data or not request.data.get(field)]
                
            if missing_fields:
                response_data = {
                'error': f"The following fields are required: {', '.join(missing_fields)}",
                'status': ResponseStatus.FAIL.value
                }
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
            
            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                response_data={
                    'result':'User registered successfully',
                    'status':ResponseStatus.SUCCESS.value
                }
                return Response(response_data, status=status.HTTP_201_CREATED)
            else:
                response_data={
                    'error':serializer.errors,
                    'status': ResponseStatus.FAIL.value
                }
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:  # Catch any other unexpected exceptions
            response_data = {
                'result': str(e),
                'status': ResponseStatus.FAIL.value
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def retrieve(self, request, uuid, *args, **kwargs):
        try:
            user = self.get_queryset().filter(id=uuid).first()
            self.check_object_permissions(request, user)
            if not user:
                response_data={
                'error':"User does not exist",
                'status': ResponseStatus.FAIL.value
                }
                return Response(response_data, status=status.HTTP_404_NOT_FOUND)
            else:
                serializer = self.get_serializer(user)
                response_data = {
                    'result':serializer.data,
                    'status':ResponseStatus.SUCCESS.value
                }
                return Response(response_data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            response_data = {
                'result':'User does not exist',
                'status':ResponseStatus.FAIL.value
            }
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)
    
    def update(self, request, uuid=None, *args, **kwargs):
        user = self.get_queryset().filter(id=uuid).first()
        self.check_object_permissions(request, user)
        if not user:
            response_data = {
                'error': "User does not exist",
                'status': ResponseStatus.FAIL.value
            }
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)

        
        # Pass the data to the serializer
        serializer = self.get_serializer(user, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save(updated_at=timezone.now())
            response_data = {
                'result': serializer.data,
                'status': ResponseStatus.SUCCESS.value
            }
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            response_data = {
                'error': serializer.errors,
                'status': ResponseStatus.FAIL.value
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

        
    def destroy(self, request, uuid=None, *args, **kwargs):
        user = self.get_queryset().filter(id=uuid).first()
        self.check_object_permissions(request, user)

        if not user:
            response_data={
                'error':"User does not exist",
                'status': ResponseStatus.FAIL.value
            }
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)
        else:
            logout_view = LogoutView.as_view()
            logout_request = request._request  # Get the original request object
            logout_response = logout_view(logout_request)

            # Log the response if necessary
            if logout_response.status_code != status.HTTP_200_OK:
                return Response({
                    'error': 'Failed to log out the user',
                    'status': ResponseStatus.FAIL.value
                }, status=logout_response.status_code)
            
            user.delete()

            response_data = {
                'result': 'User deleted successfully',
                'status': 'success'
            }
            return Response(response_data, status=status.HTTP_204_NO_CONTENT)

    def partial_update(self, request, uuid=None, *args, **kwargs):
        try:
            user = self.get_queryset().filter(id=uuid).first()
            self.check_object_permissions(request, user)
            
            if not user:
                response_data={
                    'error':"User does not exist",
                    'status': ResponseStatus.FAIL.value
                }
                return Response(response_data, status=status.HTTP_404_NOT_FOUND)
            else:
                serializer = self.get_serializer(user, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save(updated_at=timezone.now())
                    response_data = {
                        'result': serializer.data,
                        'status': ResponseStatus.SUCCESS.value
                    }
                    return Response(response_data, status=status.HTTP_200_OK)
                else:
                    response_data = {
                        'error': serializer.errors,
                        'status': ResponseStatus.FAIL.value
                    }
                    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            response_data = {
                'result': 'Given user does not exist',
                'status': ResponseStatus.FAIL.value
            }
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)
class LoginView(APIView):
    permission_classes = [AllowAny]
    serializer = UserLoginSerializer

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data.get('username')
            password = serializer.validated_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                # Create JWT tokens
                refresh = RefreshToken.for_user(user)
                user_data = UserSerializer(user).data

                response_data = {
                    'result': {
                        'message': 'Logged in successfully',
                        'user': user_data,
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    },
                    'status': ResponseStatus.SUCCESS.value
                }
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                response_data = {
                    'error': 'Invalid credentials',
                    'status': ResponseStatus.FAIL.value
                }
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
        else:
                    response_data = {
                        'error': serializer.errors,
                        'status': ResponseStatus.FAIL.value
                    }
                    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def post(self, request):
        if not request.user.is_authenticated:
                response_data = {
                    'error': 'No user is currently logged in',
                    'status': ResponseStatus.FAIL.value
                }
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = UserLogoutSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data.get('username')
            userid = serializer.validated_data.get('id')

            if str(request.user) != str(userid):
                response_data = {
                    'error': f'User {username} is not logged in',
                    'status': ResponseStatus.FAIL.value
                }
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

            # If authenticated and username matches
            token = request.META.get('HTTP_AUTHORIZATION').split()[1]
            if not token:
                return Response({
                    'error': 'Token not found',
                    'status': ResponseStatus.FAIL.value
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                if BlacklistedToken.objects.filter(token=token).exists():
                    return Response({'error': 'Token is already invalidated','status': ResponseStatus.FAIL.value}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    BlacklistedToken.objects.create(token=token)
                except Exception as e:
                    return Response({'error': str(e), 'status': ResponseStatus.FAIL.value}, status=status.HTTP_400_BAD_REQUEST)

                response_data = {
                    'result': 'Logged out successfully',
                    'status': ResponseStatus.SUCCESS.value
                }
                return Response(response_data, status=status.HTTP_200_OK)
        else:
                    response_data = {
                        'error': serializer.errors,
                        'status': ResponseStatus.FAIL.value
                    }
                    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
        
class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [IsAuthenticatedUser]
    authentication_classes = [JWTAuthentication]

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
                response_data = {
                    'error': 'User not authenticated',
                    'status': ResponseStatus.FAIL.value
                }
                return Response(response_data, status=status.HTTP_403_FORBIDDEN)
        else:
            # check if incoming access_token is not in blacklist
            access_token = request.META.get('HTTP_AUTHORIZATION').split()[1]
            if not access_token:
                return Response({
                    'error': 'Token not found',
                    'status': ResponseStatus.FAIL.value
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                if BlacklistedToken.objects.filter(token=access_token).exists():
                    return Response({'error': 'Token is already invalidated','status': ResponseStatus.FAIL.value}, status=status.HTTP_400_BAD_REQUEST)

            serializer = RefreshTokenSerializer(data=request.data)
            if serializer.is_valid():
                incoming_refresh_token = serializer.validated_data.get('refresh')
                ref_token = RefreshToken(incoming_refresh_token)
                    
                user_id=ref_token["user_id"]
                if str(user_id) != str(request.user):
                    response_data = {
                    'error': 'User not authenticated',
                    'status': ResponseStatus.FAIL.value
                    }
                    return Response(response_data, status=status.HTTP_403_FORBIDDEN)
                    
                user = User.objects.get(id=user_id)
                new_refresh = RefreshToken.for_user(user)
                response_data = {
                    'result': {
                        'accessToken': str(new_refresh.access_token),
                        'refreshToken': str(new_refresh),
                    },
                    'status': ResponseStatus.SUCCESS.value
                }
                #blacklist the previous access token and incoming refresh token
                try:
                    BlacklistedToken.objects.create(token=access_token)
                    BlacklistedToken.objects.create(token=incoming_refresh_token)
                except Exception as e:
                    return Response({'error': str(e),'status': ResponseStatus.FAIL.value}, status=status.HTTP_400_BAD_REQUEST)


                return Response(response_data, status=status.HTTP_200_OK)
            else:
                response_data = {
                        'error': serializer.errors,
                        'status': ResponseStatus.FAIL.value
                    }
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
                