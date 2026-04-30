from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from api.models import (
    Category,
    Direction,
    Frequency,
    RecurringPattern,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)

User = get_user_model()


class ModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="model-user",
            email="model@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other-model-user",
            email="other-model@example.com",
            password="StrongPass123!",
        )
        self.category = Category.objects.create(name="Food", user=self.user)

    def test_category_str(self):
        self.assertEqual(str(self.category), "Food")

    def test_category_str_with_parent(self):
        child = Category.objects.create(
            name="Restaurants", parent=self.category, user=self.user
        )
        self.assertEqual(str(child), "Food / Restaurants")

    def test_transaction_manager_methods(self):
        Transaction.objects.create(
            user=self.user,
            description="Salary",
            amount=Decimal("1000.00"),
            currency="CLP",
            transaction_type=TransactionType.CREDIT,
            direction=Direction.INCOME,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
        )
        Transaction.objects.create(
            user=self.user,
            description="Groceries",
            amount=Decimal("50.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.MERCADOPAGO,
            status=TransactionStatus.CONFIRMED,
            is_installment=True,
            installment_current=1,
            installment_total=3,
        )

        self.assertEqual(Transaction.objects.expenses().count(), 1)
        self.assertEqual(Transaction.objects.income().count(), 1)
        self.assertEqual(
            Transaction.objects.by_source(Source.MERCADOPAGO).count(),
            1,
        )
        self.assertEqual(Transaction.objects.installments_pending().count(), 1)

    def test_external_id_is_unique_per_source_when_present(self):
        Transaction.objects.create(
            user=self.user,
            description="Payment A",
            amount=Decimal("100.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            external_id="abc123",
        )

        with self.assertRaises(IntegrityError):
            Transaction.objects.create(
                user=self.user,
                description="Payment B",
                amount=Decimal("80.00"),
                currency="CLP",
                transaction_type=TransactionType.DEBIT,
                direction=Direction.EXPENSE,
                source=Source.BANK_ACCOUNT,
                external_id="abc123",
            )

    def test_same_external_id_allowed_in_different_sources(self):
        Transaction.objects.create(
            user=self.user,
            description="Payment A",
            amount=Decimal("100.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            external_id="shared",
        )
        Transaction.objects.create(
            user=self.other_user,
            description="Payment B",
            amount=Decimal("100.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.MERCADOPAGO,
            external_id="shared",
        )
        self.assertEqual(Transaction.objects.filter(external_id="shared").count(), 2)

    def test_recurring_pattern_str(self):
        pattern = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="NETFLIX",
            expected_amount=Decimal("9.99"),
            frequency=Frequency.MONTHLY,
        )
        self.assertIn("NETFLIX", str(pattern))
