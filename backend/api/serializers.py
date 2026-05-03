from decimal import Decimal

from rest_framework import serializers

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import (
    Category,
    FileImport,
    MercadoPagoStoredPayment,
    RecurringPattern,
    Source,
    Transaction,
    UserProfile,
    VisaInternationalStatement,
    VisaNacionalStatement,
    normalize_recurring_description_pattern,
)

User = get_user_model()

_NON_HIDEABLE_SOURCES_FOR_REPORTS = frozenset(
    {
        Source.CREDIT_CARD_NATIONAL,
        Source.CREDIT_CARD_INTERNATIONAL,
    }
)


class UserProfileSerializer(serializers.ModelSerializer):
    """BYOK Gemini key: write-only; response only exposes ``has_gemini_key``."""

    gemini_api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    has_gemini_key = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = ("id", "created_at", "updated_at", "has_gemini_key", "gemini_api_key")
        read_only_fields = ("id", "created_at", "updated_at", "has_gemini_key")

    def get_has_gemini_key(self, obj: UserProfile):
        return obj.has_gemini_api_key()

    def update(self, instance, validated_data):
        validated_rest = dict(validated_data)
        gemini_raw = validated_rest.pop("gemini_api_key", serializers.empty)
        # Omitting gemini_api_key on PATCH keeps the previously stored credential.
        if gemini_raw is not serializers.empty:
            instance.set_gemini_api_key(gemini_raw)
        return super().update(instance, validated_rest)


class SignUpSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")
        read_only_fields = ("id",)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class SignInSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class ImportBankStatementSerializer(serializers.Serializer):
    file = serializers.FileField()


class ImportVisaNationalStatementSerializer(serializers.Serializer):
    """Multipart upload: PDF Visa Nacional statement."""

    file = serializers.FileField()


class ImportVisaInternationalStatementSerializer(serializers.Serializer):
    """Multipart upload: PDF Visa Internacional (USD) statement."""

    file = serializers.FileField()


class FileImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileImport
        fields = (
            "id",
            "created_at",
            "updated_at",
            "user",
            "source",
            "file",
            "original_filename",
            "status",
            "rows_imported",
            "rows_skipped",
            "error_message",
        )
        read_only_fields = fields


class VisaInternationalStatementSerializer(serializers.ModelSerializer):
    original_filename = serializers.SerializerMethodField()
    uploaded_file_url = serializers.SerializerMethodField()

    class Meta:
        model = VisaInternationalStatement
        fields = (
            "id",
            "period_start",
            "period_end",
            "total_amount",
            "currency",
            "file_import",
            "original_filename",
            "uploaded_file_url",
        )
        read_only_fields = fields

    def get_original_filename(self, obj):
        if not getattr(obj, "file_import_id", None):
            return None
        return obj.file_import.original_filename

    def get_uploaded_file_url(self, obj):
        if not getattr(obj, "file_import_id", None):
            return None
        fi = obj.file_import
        if not fi.file or not getattr(fi.file, "name", None):
            return None
        url = fi.file.url
        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class VisaNacionalStatementSerializer(serializers.ModelSerializer):
    original_filename = serializers.SerializerMethodField()
    uploaded_file_url = serializers.SerializerMethodField()

    class Meta:
        model = VisaNacionalStatement
        fields = (
            "id",
            "period_end",
            "total_amount",
            "currency",
            "file_import",
            "original_filename",
            "uploaded_file_url",
        )
        read_only_fields = fields

    def get_original_filename(self, obj):
        if not getattr(obj, "file_import_id", None):
            return None
        return obj.file_import.original_filename

    def get_uploaded_file_url(self, obj):
        if not getattr(obj, "file_import_id", None):
            return None
        fi = obj.file_import
        if not fi.file or not getattr(fi.file, "name", None):
            return None
        url = fi.file.url
        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "id",
            "created_at",
            "updated_at",
            "user",
            "name",
            "parent",
            "icon",
            "color",
        )
        read_only_fields = ("id", "created_at", "updated_at", "user")

    def validate_parent(self, value):
        request = self.context.get("request")
        if value and request and value.user_id != request.user.id:
            raise serializers.ValidationError(
                "Parent category must belong to the authenticated user."
            )
        return value


class MercadoPagoStoredPaymentSlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = MercadoPagoStoredPayment
        fields = ("id", "mp_payment_id")
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    splits = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    mercadopago_stored_payment = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = (
            "id",
            "created_at",
            "updated_at",
            "user",
            "description",
            "amount",
            "currency",
            "amount_local",
            "exchange_rate",
            "transaction_type",
            "direction",
            "category",
            "subcategory",
            "source",
            "original_reference",
            "external_id",
            "external_name",
            "is_installment",
            "installment_current",
            "installment_total",
            "installment_amount",
            "installment_group_id",
            "raw_data",
            "imported_at",
            "transaction_date",
            "status",
            "parent",
            "file_import",
            "visa_international_statement",
            "visa_nacional_statement",
            "matched_recurring_pattern",
            "is_hidden",
            "splits",
            "mercadopago_stored_payment",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "user",
            "splits",
            "external_name",
            "file_import",
            "visa_international_statement",
            "visa_nacional_statement",
            "matched_recurring_pattern",
            "mercadopago_stored_payment",
        )

    def get_mercadopago_stored_payment(self, obj: Transaction):
        try:
            sp = obj.mercadopago_stored_payment
        except MercadoPagoStoredPayment.DoesNotExist:
            return None
        return MercadoPagoStoredPaymentSlimSerializer(sp).data

    def validate(self, attrs):
        instance = self.instance
        if instance is None:
            src = attrs.get("source")
            hidden = attrs.get("is_hidden", False)
        else:
            src = attrs.get("source", instance.source)
            hidden = attrs.get("is_hidden", instance.is_hidden)
        if hidden and src in _NON_HIDEABLE_SOURCES_FOR_REPORTS:
            raise serializers.ValidationError(
                {
                    "is_hidden": (
                        "National or international Visa card transactions "
                        "cannot be hidden."
                    ),
                },
            )
        return attrs

    def validate_category(self, value):
        request = self.context.get("request")
        if value and request and value.user_id != request.user.id:
            raise serializers.ValidationError(
                "Category must belong to the authenticated user."
            )
        return value

    def validate_parent(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError(
                "Parent transaction must belong to the authenticated user."
            )
        if value.parent_id is not None:
            raise serializers.ValidationError(
                "Parent must be a top-level transaction (not a split line)."
            )
        return value


class TransactionSplitItemSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    category = serializers.UUIDField(allow_null=True, required=False)


class TransactionSplitRequestSerializer(serializers.Serializer):
    items = TransactionSplitItemSerializer(many=True)


class RecurringPatternSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringPattern
        fields = (
            "id",
            "created_at",
            "updated_at",
            "user",
            "description_pattern",
            "expected_amount",
            "frequency",
            "match_type",
        )
        read_only_fields = ("id", "created_at", "updated_at", "user")

    def validate_description_pattern(self, value: str) -> str:
        normalized = normalize_recurring_description_pattern(value)
        if not normalized:
            raise serializers.ValidationError("This field may not be blank.")
        return normalized
