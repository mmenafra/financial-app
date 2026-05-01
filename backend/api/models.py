import base64
import hashlib
import uuid

from cryptography.fernet import Fernet

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


def _fernet_for_api_keys() -> Fernet:
    """Symmetric key derived from Django SECRET_KEY (server-side-at-rest encryption)."""

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


class AbstractBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SocialAccount(AbstractBaseModel):
    """Links a Django user to an external identity (e.g. Google Sign-In)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_accounts",
    )
    provider = models.CharField(max_length=50)
    provider_uid = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_uid"],
                name="api_socialaccount_provider_provider_uid_uniq",
            )
        ]

    def __str__(self):
        return f"{self.provider}:{self.provider_uid}"


class UserProfile(AbstractBaseModel):
    """Per-user preferences and secrets encrypted at rest (BYOK Gemini key)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    _gemini_api_key = models.BinaryField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "user_profiles"

    def set_gemini_api_key(self, raw_key: str) -> None:
        if not raw_key or not raw_key.strip():
            self._gemini_api_key = None
            return
        fernet = _fernet_for_api_keys()
        self._gemini_api_key = fernet.encrypt(raw_key.strip().encode("utf-8"))

    def get_gemini_api_key(self) -> str | None:
        """Decrypt API key — use only server-side."""

        if not self._gemini_api_key:
            return None
        fernet = _fernet_for_api_keys()
        return fernet.decrypt(bytes(self._gemini_api_key)).decode("utf-8")

    def has_gemini_api_key(self) -> bool:
        return bool(self._gemini_api_key)


class Category(AbstractBaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="categories",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    icon = models.CharField(max_length=50, null=True, blank=True)
    color = models.CharField(max_length=7, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "categories"

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} / {self.name}"
        return self.name


class TransactionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CANCELLED = "CANCELLED", "Cancelled"


class TransactionType(models.TextChoices):
    DEBIT = "DEBIT", "Debit"
    CREDIT = "CREDIT", "Credit"
    TRANSFER = "TRANSFER", "Transfer"


class Direction(models.TextChoices):
    INCOME = "INCOME", "Income"
    EXPENSE = "EXPENSE", "Expense"


class Source(models.TextChoices):
    MERCADOPAGO = "MERCADOPAGO", "MercadoPago"
    BANK_ACCOUNT = "BANK_ACCOUNT", "Bank account"
    CREDIT_CARD_NATIONAL = "CREDIT_CARD_NATIONAL", "Credit card national"
    CREDIT_CARD_INTERNATIONAL = (
        "CREDIT_CARD_INTERNATIONAL",
        "Credit card international",
    )


class Frequency(models.TextChoices):
    DAILY = "DAILY", "Daily"
    WEEKLY = "WEEKLY", "Weekly"
    MONTHLY = "MONTHLY", "Monthly"
    YEARLY = "YEARLY", "Yearly"


class ImportStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class FileImport(AbstractBaseModel):
    """Recorded file upload for statement/import flows (metadata + stored copy)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="file_imports",
    )
    source = models.CharField(max_length=30, choices=Source.choices)
    file = models.FileField(upload_to="imports/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=ImportStatus.choices,
        default=ImportStatus.PENDING,
    )
    rows_imported = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.source})"


class VisaInternationalStatement(AbstractBaseModel):
    """One Visa Internacional (USD) statement per uploaded PDF (`FileImport`)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="visa_international_statements",
    )
    file_import = models.OneToOneField(
        FileImport,
        on_delete=models.CASCADE,
        related_name="visa_international_statement",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    class Meta:
        ordering = ["-period_end", "-created_at"]

    @property
    def uploaded_file(self):
        """Underlying upload on the linked :class:`FileImport` (same blob as ``file_import.file``)."""
        if not self.file_import_id:
            return None
        return self.file_import.file

    def __str__(self):
        return f"Visa Intl {self.period_start}–{self.period_end} ({self.total_amount} {self.currency})"


class VisaNacionalStatement(AbstractBaseModel):
    """One Visa Nacional (CLP) statement per uploaded PDF (`FileImport`)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="visa_nacional_statements",
    )
    file_import = models.OneToOneField(
        FileImport,
        on_delete=models.CASCADE,
        related_name="visa_nacional_statement",
    )
    period_end = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="CLP")

    class Meta:
        ordering = ["-period_end", "-created_at"]

    def __str__(self):
        return (
            f"Visa Nac cierre {self.period_end} ({self.total_amount} {self.currency})"
        )


class TransactionQuerySet(models.QuerySet):
    def expenses(self):
        return self.filter(direction=Direction.EXPENSE)

    def income(self):
        return self.filter(direction=Direction.INCOME)

    def by_source(self, source):
        return self.filter(source=source)

    def installments_pending(self):
        return self.filter(is_installment=True, status=TransactionStatus.CONFIRMED)

    def leaf_only(self):
        """Exclude bundle transactions that have been split into children."""
        return self.filter(splits__isnull=True)


class TransactionManager(models.Manager):
    def get_queryset(self):
        return TransactionQuerySet(self.model, using=self._db)

    def expenses(self):
        return self.get_queryset().expenses()

    def income(self):
        return self.get_queryset().income()

    def by_source(self, source):
        return self.get_queryset().by_source(source)

    def installments_pending(self):
        return self.get_queryset().installments_pending()


class Transaction(AbstractBaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    amount_local = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    subcategory = models.CharField(max_length=100, null=True, blank=True)
    source = models.CharField(max_length=30, choices=Source.choices)
    original_reference = models.CharField(max_length=255, null=True, blank=True)
    external_id = models.CharField(max_length=255, null=True, blank=True)
    external_name = models.CharField(max_length=255, null=True, blank=True)
    is_installment = models.BooleanField(default=False)
    installment_current = models.PositiveSmallIntegerField(null=True, blank=True)
    installment_total = models.PositiveSmallIntegerField(null=True, blank=True)
    installment_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    installment_group_id = models.UUIDField(null=True, blank=True)
    raw_data = models.JSONField(null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    transaction_date = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=10,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="splits",
    )
    file_import = models.ForeignKey(
        FileImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    visa_international_statement = models.ForeignKey(
        VisaInternationalStatement,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transactions",
    )
    visa_nacional_statement = models.ForeignKey(
        VisaNacionalStatement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    matched_recurring_pattern = models.ForeignKey(
        "RecurringPattern",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_transactions",
        db_index=True,
    )

    objects = TransactionManager()

    class Meta:
        ordering = ["-transaction_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source", "external_id"],
                condition=Q(external_id__isnull=False) & ~Q(external_id=""),
                name="unique_external_id_per_user_source_when_present",
            )
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.external_name is None:
            self.external_name = self.description
        if self._state.adding and self.transaction_date is None:
            self.transaction_date = timezone.now().date()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} ({self.amount} {self.currency})"


class RecurringPattern(AbstractBaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recurring_patterns",
        null=True,
        blank=True,
    )
    description_pattern = models.CharField(max_length=255)
    expected_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    frequency = models.CharField(max_length=10, choices=Frequency.choices)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.description_pattern} [{self.frequency}]"


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):  # pylint: disable=unused-argument
    if created:
        UserProfile.objects.get_or_create(user=instance)
