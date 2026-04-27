import logging
import os
from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiRequest,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .bank_statement_parser import parse_bsa_bank_statement
from .bsa_import import import_bsa_row
from .models import (
    Category,
    RecurringPattern,
    SocialAccount,
    Source,
    Transaction,
)
from .pagination import TransactionPagination
from .serializers import (
    CategorySerializer,
    ForgotPasswordSerializer,
    GoogleAuthSerializer,
    ImportBankStatementSerializer,
    ImportVisaInternationalStatementSerializer,
    ImportVisaNationalStatementSerializer,
    RecurringPatternSerializer,
    ResetPasswordSerializer,
    SignInSerializer,
    SignUpSerializer,
    TransactionSerializer,
    TransactionSplitRequestSerializer,
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


class ImportBankStatementView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=OpenApiRequest(
            request=ImportBankStatementSerializer,
            encoding={"file": {"contentType": "application/octet-stream"}},
        ),
        responses={
            201: inline_serializer(
                name="ImportBankStatementPersistResponse",
                fields={
                    "created": serializers.IntegerField(),
                    "skipped": serializers.IntegerField(),
                    "failed": serializers.IntegerField(),
                    "transactions": TransactionSerializer(many=True),
                    "errors": serializers.ListField(
                        child=inline_serializer(
                            name="ImportBankStatementRowError",
                            fields={
                                "row": serializers.JSONField(),
                                "error": serializers.CharField(),
                            },
                        )
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

        created_count = 0
        skipped_count = 0
        failed_count = 0
        created_instances = []
        errors: list[dict] = []
        for row in parsed.get("transactions", []):
            result = import_bsa_row(request.user, row)
            if "error" in result:
                failed_count += 1
                errors.append({"row": row, "error": result["error"]})
                continue
            if result.get("ok") == "skipped":
                skipped_count += 1
            elif result.get("ok") == "created" and result.get("instance"):
                created_count += 1
                created_instances.append(result["instance"])

        logger.info(
            "Import bank statement persist: user_id=%s created=%s skipped=%s failed=%s",
            request.user.pk,
            created_count,
            skipped_count,
            failed_count,
        )
        ser = TransactionSerializer(
            created_instances, many=True, context={"request": request}
        )
        return Response(
            {
                "created": created_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "transactions": ser.data,
                "errors": errors,
            },
            status=status.HTTP_201_CREATED,
        )


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


_SOURCE_QUERY_ENUM = [choice.value for choice in Source]


def _query_param_non_empty(raw):
    return raw is not None and str(raw).strip() != ""


def _apply_transaction_year_filter(qs, year_raw):
    if not _query_param_non_empty(year_raw):
        return qs
    try:
        year = int(year_raw)
    except (TypeError, ValueError) as err:
        raise ValidationError(
            {"year": "Must be a valid integer."}
        ) from err
    if year < 1 or year > 9999:
        raise ValidationError({"year": "Invalid year."})
    return qs.filter(created_at__year=year)


def _apply_transaction_month_filter(qs, month_raw):
    if not _query_param_non_empty(month_raw):
        return qs
    try:
        month = int(month_raw)
    except (TypeError, ValueError) as err:
        raise ValidationError(
            {"month": "Must be a valid integer."}
        ) from err
    if month < 1 or month > 12:
        raise ValidationError({"month": "Must be between 1 and 12."})
    return qs.filter(created_at__month=month)


def _apply_transaction_category_filter(qs, category_id, user):
    if not _query_param_non_empty(category_id):
        return qs
    if not Category.objects.filter(pk=category_id, user=user).exists():
        raise ValidationError(
            {"category": "Category must belong to the authenticated user."}
        )
    return qs.filter(category_id=category_id)


def _apply_transaction_source_filter(qs, source_raw):
    if not _query_param_non_empty(source_raw):
        return qs
    if source_raw not in _SOURCE_QUERY_ENUM:
        raise ValidationError(
            {
                "source": (
                    "Invalid source. Must be one of: "
                    f"{', '.join(_SOURCE_QUERY_ENUM)}."
                )
            }
        )
    return qs.filter(source=source_raw)


def _filter_transactions_list_queryset(qs, query_params, user):
    """Apply optional GET /transactions/ filters. Raises ValidationError if invalid."""
    year_raw = query_params.get("year")
    month_raw = query_params.get("month")
    if _query_param_non_empty(month_raw) and not _query_param_non_empty(year_raw):
        raise ValidationError(
            {"month": "year is required when month is provided."}
        )
    qs = _apply_transaction_year_filter(qs, year_raw)
    qs = _apply_transaction_month_filter(qs, month_raw)
    qs = _apply_transaction_category_filter(
        qs, query_params.get("category"), user
    )
    qs = _apply_transaction_source_filter(qs, query_params.get("source"))
    return qs


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="year",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Filter by calendar year of `created_at` (UTC). "
                    "Use together with `month` to restrict to a single month."
                ),
                examples=[OpenApiExample("Current year", value=2026)],
            ),
            OpenApiParameter(
                name="month",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Filter by calendar month (1–12) of `created_at` (UTC). "
                    "Requires `year` to be set."
                ),
                examples=[OpenApiExample("April", value=4)],
            ),
            OpenApiParameter(
                name="category",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by category id (must be one of your categories).",
            ),
            OpenApiParameter(
                name="source",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by transaction source.",
                enum=_SOURCE_QUERY_ENUM,
                examples=[OpenApiExample("Mercado Pago", value=Source.MERCADOPAGO.value)],
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Page number (1-based).",
                examples=[OpenApiExample("First page", value=1)],
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Number of results per page. "
                    "Capped at the API maximum (e.g. 100)."
                ),
                examples=[OpenApiExample("Default size", value=100)],
            ),
        ],
    ),
)
class TransactionViewSet(ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TransactionPagination

    def get_queryset(self):
        qs = Transaction.objects.filter(user=self.request.user)
        if self.action != "list":
            return qs
        qs = qs.filter(splits__isnull=True)
        return _filter_transactions_list_queryset(
            qs, self.request.query_params, self.request.user
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Aggregate total expenses for the current filter period.
        total_spent = (
            queryset.filter(direction="EXPENSE")
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

        # Aggregate expenses for the previous calendar month (same category/source).
        year_raw = request.query_params.get("year")
        month_raw = request.query_params.get("month")
        prev_spent = Decimal("0")
        if _query_param_non_empty(year_raw) and _query_param_non_empty(month_raw):
            year = int(year_raw)
            month = int(month_raw)
            prev_year = year - 1 if month == 1 else year
            prev_month = 12 if month == 1 else month - 1
            prev_qs = Transaction.objects.filter(
                user=request.user, splits__isnull=True
            ).filter(created_at__year=prev_year, created_at__month=prev_month)
            prev_qs = _apply_transaction_category_filter(
                prev_qs, request.query_params.get("category"), request.user
            )
            prev_qs = _apply_transaction_source_filter(
                prev_qs, request.query_params.get("source")
            )
            prev_spent = (
                prev_qs.filter(direction="EXPENSE")
                .aggregate(total=Sum("amount"))["total"]
                or Decimal("0")
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data["total_spent"] = str(total_spent)
            response.data["prev_month_spent"] = str(prev_spent)
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "results": serializer.data,
                "total_spent": str(total_spent),
                "prev_month_spent": str(prev_spent),
            }
        )

    @extend_schema(
        request=TransactionSplitRequestSerializer,
        responses={201: TransactionSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="split")
    @db_transaction.atomic
    def split(self, request, pk=None):
        """Split a top-level transaction into multiple lines (strict amount match)."""
        bundle = self.get_object()
        if bundle.parent_id is not None:
            raise ValidationError(
                {"detail": "Cannot split a transaction that is already a split line."}
            )
        if bundle.splits.exists():
            raise ValidationError({"detail": "This transaction is already split."})

        ser = TransactionSplitRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        items = ser.validated_data["items"]
        if len(items) < 2:
            raise ValidationError(
                {"items": "At least two split lines are required."}
            )

        total = sum((row["amount"] for row in items), Decimal("0"))
        if total != bundle.amount:
            raise ValidationError(
                {
                    "items": "Sum of split amounts must equal the transaction amount."
                }
            )

        created = []
        for row in items:
            cat_id = row.get("category")
            category = None
            if cat_id is not None:
                try:
                    category = Category.objects.get(pk=cat_id, user=request.user)
                except Category.DoesNotExist as err:
                    raise ValidationError(
                        {
                            "items": "Each category must belong to the authenticated user."
                        }
                    ) from err

            child = Transaction.objects.create(
                user=bundle.user,
                description=row["description"],
                amount=row["amount"],
                currency=bundle.currency,
                amount_local=None,
                exchange_rate=bundle.exchange_rate,
                transaction_type=bundle.transaction_type,
                direction=bundle.direction,
                category=category,
                subcategory=None,
                source=bundle.source,
                original_reference=bundle.original_reference,
                external_id=None,
                is_installment=False,
                installment_current=None,
                installment_total=None,
                installment_amount=None,
                installment_group_id=None,
                raw_data=None,
                imported_at=bundle.imported_at,
                status=bundle.status,
                parent=bundle,
            )
            created.append(child)

        out = TransactionSerializer(
            created, many=True, context={"request": request}
        )
        return Response(out.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RecurringPatternViewSet(ModelViewSet):
    serializer_class = RecurringPatternSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RecurringPattern.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
