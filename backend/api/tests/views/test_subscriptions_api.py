"""Tests for GET /api/subscriptions/."""

from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from api.models import (
    Direction,
    FileImport,
    Frequency,
    ImportStatus,
    RecurringPattern,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
    VisaInternationalStatement,
    VisaNacionalStatement,
)

User = get_user_model()


class SubscriptionsAPITests(APITestCase):  # pylint: disable=too-many-public-methods
    def setUp(self):
        self.user = User.objects.create_user(
            username="subs-user",
            email="subs@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="subs-other",
            email="subs-other@example.com",
            password="StrongPass123!",
        )
        self.url = reverse("subscription-list")

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_empty_when_no_visa_statements(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_lists_pattern_from_latest_nacional_statement(self):
        pat = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="NETFLIX%",
            expected_amount=Decimal("15000"),
            frequency=Frequency.MONTHLY,
        )
        fi = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_NATIONAL,
            file=ContentFile(b"x", name="vn.pdf"),
            original_filename="vn.pdf",
            status=ImportStatus.COMPLETED,
        )
        stmt = VisaNacionalStatement.objects.create(
            user=self.user,
            file_import=fi,
            period_end=date(2026, 2, 28),
            total_amount=Decimal("50000.00"),
            currency="CLP",
        )
        Transaction.objects.create(
            user=self.user,
            description="NETFLIX CL",
            amount=Decimal("14990.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_NATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2026, 2, 15),
            visa_nacional_statement=stmt,
            matched_recurring_pattern=pat,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertEqual(row["name"], "NETFLIX%")
        self.assertEqual(row["currency"], "CLP")
        self.assertEqual(Decimal(row["amount"]), Decimal("14990.00"))
        self.assertEqual(row["frequency"], Frequency.MONTHLY)
        self.assertEqual(row["last_matched_date"], "2026-02-15")

    def test_ignores_older_statement(self):
        pat = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="OLD%",
            expected_amount=None,
            frequency=Frequency.MONTHLY,
        )
        fi_old = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"a", name="old.pdf"),
            original_filename="old.pdf",
            status=ImportStatus.COMPLETED,
        )
        stmt_old = VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi_old,
            period_start=date(2025, 12, 1),
            period_end=date(2025, 12, 31),
            total_amount=Decimal("80.00"),
        )
        fi_new = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"b", name="new.pdf"),
            original_filename="new.pdf",
            status=ImportStatus.COMPLETED,
        )
        VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi_new,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            total_amount=Decimal("90.00"),
        )
        Transaction.objects.create(
            user=self.user,
            description="OLD SUB",
            amount=Decimal("10.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 12, 10),
            visa_international_statement=stmt_old,
            matched_recurring_pattern=pat,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_deduplicates_multiple_matches_same_pattern(self):
        pat = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="DOUBLE%",
            expected_amount=None,
            frequency=Frequency.MONTHLY,
        )
        fi = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"z", name="st.pdf"),
            original_filename="st.pdf",
            status=ImportStatus.COMPLETED,
        )
        stmt = VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            total_amount=Decimal("120.00"),
        )
        Transaction.objects.create(
            user=self.user,
            description="Double A",
            amount=Decimal("5.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2026, 2, 5),
            visa_international_statement=stmt,
            matched_recurring_pattern=pat,
        )
        Transaction.objects.create(
            user=self.user,
            description="Double B",
            amount=Decimal("8.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2026, 2, 20),
            visa_international_statement=stmt,
            matched_recurring_pattern=pat,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(Decimal(response.data[0]["amount"]), Decimal("8.00"))

    def test_user_only_sees_own_subscriptions(self):
        pat_own = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="MINE%",
            expected_amount=None,
            frequency=Frequency.MONTHLY,
        )
        pat_other = RecurringPattern.objects.create(
            user=self.other_user,
            description_pattern="THEIRS%",
            expected_amount=None,
            frequency=Frequency.MONTHLY,
        )

        fi = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_NATIONAL,
            file=ContentFile(b"u", name="mine.pdf"),
            original_filename="mine.pdf",
            status=ImportStatus.COMPLETED,
        )
        stmt = VisaNacionalStatement.objects.create(
            user=self.user,
            file_import=fi,
            period_end=date(2026, 3, 31),
            total_amount=Decimal("100000.00"),
        )
        Transaction.objects.create(
            user=self.user,
            description="Mine",
            amount=Decimal("1.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_NATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2026, 3, 1),
            visa_nacional_statement=stmt,
            matched_recurring_pattern=pat_own,
        )
        Transaction.objects.create(
            user=self.other_user,
            description="Theirs",
            amount=Decimal("99.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2026, 3, 1),
            matched_recurring_pattern=pat_other,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "MINE%")
