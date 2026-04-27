from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers

from .models import Category, FileImport, RecurringPattern, Transaction

User = get_user_model()


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


class TransactionSerializer(serializers.ModelSerializer):
    splits = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

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
            "status",
            "parent",
            "file_import",
            "splits",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "user",
            "splits",
            "external_name",
            "file_import",
        )

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
            "category",
            "expected_amount",
            "frequency",
        )
        read_only_fields = ("id", "created_at", "updated_at", "user")

    def validate_category(self, value):
        request = self.context.get("request")
        if value and request and value.user_id != request.user.id:
            raise serializers.ValidationError(
                "Category must belong to the authenticated user."
            )
        return value
