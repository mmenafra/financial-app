import logging
import os

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import serializers, status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from ..models import SocialAccount, UserProfile
from ..serializers import (
    ForgotPasswordSerializer,
    GoogleAuthSerializer,
    ResetPasswordSerializer,
    SignInSerializer,
    SignUpSerializer,
    UserProfileSerializer,
)

User = get_user_model()

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """Simple endpoint to verify API is reachable."""

    @extend_schema(
        responses={
            200: inline_serializer(
                name="HealthCheckResponse",
                fields={
                    "status": serializers.CharField(),
                    "service": serializers.CharField(),
                },
            )
        }
    )
    def get(self, request):
        return Response({"status": "ok", "service": "finance-app-api"})


class SignUpView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=SignUpSerializer,
        responses={
            201: inline_serializer(
                name="AuthResponse",
                fields={
                    "user": inline_serializer(
                        name="AuthUser",
                        fields={
                            "id": serializers.IntegerField(),
                            "username": serializers.CharField(),
                            "email": serializers.EmailField(),
                        },
                    ),
                    "tokens": inline_serializer(
                        name="AuthTokens",
                        fields={
                            "refresh": serializers.CharField(),
                            "access": serializers.CharField(),
                        },
                    ),
                },
            )
        },
    )
    def post(self, request):
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class SignInView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=SignInSerializer,
        responses={
            200: inline_serializer(
                name="SignInResponse",
                fields={
                    "user": inline_serializer(
                        name="SignInUser",
                        fields={
                            "id": serializers.IntegerField(),
                            "username": serializers.CharField(),
                            "email": serializers.EmailField(),
                        },
                    ),
                    "tokens": inline_serializer(
                        name="SignInTokens",
                        fields={
                            "refresh": serializers.CharField(),
                            "access": serializers.CharField(),
                        },
                    ),
                },
            ),
            401: OpenApiResponse(description="Invalid credentials"),
        },
    )
    def post(self, request):
        serializer = SignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if not user:
            logger.warning(
                "Sign-in failed: invalid credentials for username=%r",
                serializer.validated_data["username"],
            )
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            }
        )


class UserProfileView(RetrieveUpdateAPIView):
    """Read/update BYOK Gemini API key metadata (credential never exposed in GET)."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        profile, _created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile


class GoogleAuthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=GoogleAuthSerializer,
        responses={
            200: inline_serializer(
                name="GoogleAuthResponse",
                fields={
                    "user": inline_serializer(
                        name="GoogleAuthUser",
                        fields={
                            "id": serializers.IntegerField(),
                            "username": serializers.CharField(),
                            "email": serializers.EmailField(),
                        },
                    ),
                    "tokens": inline_serializer(
                        name="GoogleAuthTokens",
                        fields={
                            "refresh": serializers.CharField(),
                            "access": serializers.CharField(),
                        },
                    ),
                },
            ),
            400: OpenApiResponse(description="Bad request"),
            401: OpenApiResponse(description="Invalid token"),
            503: OpenApiResponse(description="Google Sign-In not configured"),
        },
    )
    def post(self, request):
        if not settings.GOOGLE_CLIENT_ID:
            return Response(
                {"detail": "Google Sign-In is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        id_token_str = serializer.validated_data["id_token"]

        try:
            idinfo = google_id_token.verify_oauth2_token(
                id_token_str,
                google_auth_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
        except ValueError as exc:
            logger.warning("Google id_token verification failed: %s", exc)
            return Response(
                {"detail": "Invalid Google token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        sub = idinfo.get("sub")
        email = idinfo.get("email")
        email_verified = idinfo.get("email_verified", False)
        if not sub or not email:
            return Response(
                {"detail": "Token missing required claims."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not email_verified:
            return Response(
                {"detail": "Email is not verified with Google."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        first_name = (idinfo.get("given_name") or "")[:150]
        last_name = (idinfo.get("family_name") or "")[:150]

        social = (
            SocialAccount.objects.filter(provider="google", provider_uid=sub)
            .select_related("user")
            .first()
        )
        if social:
            user = social.user
        else:
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                user = User(
                    username=email,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                )
                user.set_unusable_password()
                user.save()
            SocialAccount.objects.get_or_create(
                provider="google",
                provider_uid=sub,
                defaults={"user": user},
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            }
        )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=ForgotPasswordSerializer,
        responses={
            200: inline_serializer(
                name="ForgotPasswordResponse",
                fields={"detail": serializers.CharField()},
            )
        },
        examples=[
            OpenApiExample(
                "Request",
                value={"email": "john@example.com"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            frontend_url = os.environ.get(
                "PASSWORD_RESET_URL", "http://localhost:3000/reset-password"
            )
            reset_link = f"{frontend_url}?uid={uid}&token={token}"
            send_mail(
                subject="Password reset request",
                message=f"Use this link to reset your password: {reset_link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )

        return Response(
            {"detail": "If the email exists, password reset instructions were sent."},
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=ResetPasswordSerializer,
        responses={
            200: inline_serializer(
                name="ResetPasswordResponse",
                fields={"detail": serializers.CharField()},
            ),
            400: OpenApiResponse(description="Invalid or expired token"),
        },
    )
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uid = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {"detail": "Invalid reset link."}, status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"detail": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response(
            {"detail": "Password reset successful."}, status=status.HTTP_200_OK
        )
