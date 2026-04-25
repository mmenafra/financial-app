import logging
import os

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiRequest,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .bank_statement_parser import parse_bsa_bank_statement
from .models import Category, RecurringPattern, Transaction
from .serializers import (
    CategorySerializer,
    ForgotPasswordSerializer,
    ImportBankStatementSerializer,
    ImportVisaInternationalStatementSerializer,
    ImportVisaNationalStatementSerializer,
    RecurringPatternSerializer,
    ResetPasswordSerializer,
    SignInSerializer,
    SignUpSerializer,
    TransactionSerializer,
)
from .visa_internacional_parser import parse_visa_internacional_statement_pdf
from .visa_nacional_parser import parse_visa_nacional_statement_pdf

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


class ImportBankStatementView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=OpenApiRequest(
            request=ImportBankStatementSerializer,
            encoding={"file": {"contentType": "application/octet-stream"}},
        ),
        responses={
            200: inline_serializer(
                name="ImportBankStatementResponse",
                fields={
                    "metadata": serializers.JSONField(),
                    "transactions": serializers.ListField(
                        child=serializers.JSONField()
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid file payload"),
        },
    )
    def post(self, request):
        statement_file = request.FILES.get("file")
        if not statement_file:
            return Response(
                {"detail": "A file is required in form-data with key 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not statement_file.name.lower().endswith(".dat"):
            return Response(
                {"detail": "Only .dat files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import bank statement: user_id=%s filename=%r",
            request.user.pk,
            statement_file.name,
        )
        try:
            content = statement_file.read().decode("utf-8")
            logger.debug(
                "Bank statement file decoded, length=%s characters", len(content)
            )
            parsed = parse_bsa_bank_statement(content)
        except UnicodeDecodeError as exc:
            logger.error("Bank statement UTF-8 decode failed: %s", exc)
            return Response(
                {"detail": "File must be UTF-8 encoded text."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as exc:
            logger.error("Bank statement parse failed: %s", exc)
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import bank statement success: transactions=%s",
            len(parsed.get("transactions", [])),
        )
        return Response(parsed, status=status.HTTP_200_OK)


class ImportVisaNationalStatementView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=OpenApiRequest(
            request=ImportVisaNationalStatementSerializer,
            encoding={"file": {"contentType": "application/pdf"}},
        ),
        responses={
            200: inline_serializer(
                name="ImportVisaNationalResponse",
                fields={
                    "transactions": serializers.ListField(
                        child=serializers.JSONField()
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid file payload or PDF"),
        },
    )
    def post(self, request):
        statement_file = request.FILES.get("file")
        if not statement_file:
            return Response(
                {"detail": "A file is required in form-data with key 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not statement_file.name.lower().endswith(".pdf"):
            return Response(
                {"detail": "Only .pdf files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import Visa Nacional: user_id=%s filename=%r",
            request.user.pk,
            statement_file.name,
        )
        try:
            pdf_bytes = statement_file.read()
            logger.debug("Visa Nacional PDF size=%s bytes", len(pdf_bytes))
            parsed = parse_visa_nacional_statement_pdf(pdf_bytes)
        except ValueError as exc:
            logger.error("Visa Nacional import failed: %s", exc)
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import Visa Nacional success: transactions=%s",
            len(parsed.get("transactions", [])),
        )
        return Response(parsed, status=status.HTTP_200_OK)


class ImportVisaInternationalStatementView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=OpenApiRequest(
            request=ImportVisaInternationalStatementSerializer,
            encoding={"file": {"contentType": "application/pdf"}},
        ),
        responses={
            200: inline_serializer(
                name="ImportVisaInternationalResponse",
                fields={
                    "transactions": serializers.ListField(
                        child=serializers.JSONField()
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid file payload or PDF"),
        },
    )
    def post(self, request):
        statement_file = request.FILES.get("file")
        if not statement_file:
            return Response(
                {"detail": "A file is required in form-data with key 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not statement_file.name.lower().endswith(".pdf"):
            return Response(
                {"detail": "Only .pdf files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import Visa Internacional: user_id=%s filename=%r",
            request.user.pk,
            statement_file.name,
        )
        try:
            pdf_bytes = statement_file.read()
            logger.debug("Visa Internacional PDF size=%s bytes", len(pdf_bytes))
            parsed = parse_visa_internacional_statement_pdf(pdf_bytes)
        except ValueError as exc:
            logger.error("Visa Internacional import failed: %s", exc)
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import Visa Internacional success: transactions=%s",
            len(parsed.get("transactions", [])),
        )
        return Response(parsed, status=status.HTTP_200_OK)


class CategoryViewSet(ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TransactionViewSet(ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RecurringPatternViewSet(ModelViewSet):
    serializer_class = RecurringPatternSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RecurringPattern.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
