import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class AbstractBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


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


class TransactionQuerySet(models.QuerySet):
    def expenses(self):
        return self.filter(direction=Direction.EXPENSE)

    def income(self):
        return self.filter(direction=Direction.INCOME)

    def by_source(self, source):
        return self.filter(source=source)

    def installments_pending(self):
        return self.filter(is_installment=True, status=TransactionStatus.CONFIRMED)


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
    status = models.CharField(
        max_length=10,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
    )

    objects = TransactionManager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source", "external_id"],
                condition=Q(external_id__isnull=False) & ~Q(external_id=""),
                name="unique_external_id_per_user_source_when_present",
            )
        ]

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
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="recurring_patterns",
    )
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
