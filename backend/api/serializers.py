from rest_framework import serializers

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import Category, RecurringPattern, Transaction

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
            "is_installment",
            "installment_current",
            "installment_total",
            "installment_amount",
            "installment_group_id",
            "raw_data",
            "imported_at",
            "status",
        )
        read_only_fields = ("id", "created_at", "updated_at", "user")

    def validate_category(self, value):
        request = self.context.get("request")
        if value and request and value.user_id != request.user.id:
            raise serializers.ValidationError(
                "Category must belong to the authenticated user."
            )
        return value


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
