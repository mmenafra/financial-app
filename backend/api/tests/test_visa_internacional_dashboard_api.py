from datetime import date, datetime
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from api.models import (
    Direction,
    FileImport,
    ImportStatus,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
    VisaInternationalStatement,
)

User = get_user_model()


class VisaInternationalDashboardAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="vi-dash-user",
            email="vi-dash@example.com",
            password="StrongPass123!",
        )
        self.url = reverse("visa-international-dashboard")

    def test_requires_authentication(self):
        response = self.client.get(self.url, {"year": "2026", "month": "3"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_requires_year_and_month(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_returns_statement_transactions_and_monthly_totals(self):
        fi = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"%PDF", name="st.pdf"),
            original_filename="st.pdf",
            status=ImportStatus.COMPLETED,
        )
        stmt = VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi,
            period_start=date(2026, 2, 24),
            period_end=date(2026, 3, 23),
            total_amount=Decimal("16.15"),
        )
        tx = Transaction.objects.create(
            user=self.user,
            description="NETFLIX",
            amount=Decimal("16.15"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
            visa_international_statement=stmt,
            external_id="000000001498572431",
        )
        Transaction.objects.filter(pk=tx.pk).update(
            created_at=timezone.make_aware(datetime(2026, 3, 15, 12, 0, 0))
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"year": "2026", "month": "3"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.data
        self.assertIsNotNone(body["statement"])
        self.assertEqual(str(body["statement"]["id"]), str(stmt.id))
        self.assertEqual(body["statement"]["period_end"], "2026-03-23")
        self.assertEqual(len(body["transactions"]), 1)
        self.assertEqual(len(body["monthly_totals"]), 12)
        last = body["monthly_totals"][-1]
        self.assertEqual(last["year"], 2026)
        self.assertEqual(last["month"], 3)
        self.assertEqual(last["total"], "16.15")

    def test_no_statement_month_returns_empty_transactions(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"year": "2020", "month": "1"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["statement"])
        self.assertEqual(response.data["transactions"], [])
        self.assertEqual(len(response.data["monthly_totals"]), 12)

    def test_no_statement_falls_back_to_calendar_month_transactions(self):
        tx = Transaction.objects.create(
            user=self.user,
            description="LEGACY ROW",
            amount=Decimal("99.50"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
            visa_international_statement=None,
            external_id="legacy-dash-001",
        )
        Transaction.objects.filter(pk=tx.pk).update(
            created_at=timezone.make_aware(datetime(2020, 1, 15, 12, 0, 0))
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"year": "2020", "month": "1"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["statement"])
        self.assertEqual(len(response.data["transactions"]), 1)
        self.assertEqual(response.data["transactions"][0]["description"], "LEGACY ROW")
        last = response.data["monthly_totals"][-1]
        self.assertEqual(last["year"], 2020)
        self.assertEqual(last["month"], 1)
        self.assertEqual(last["total"], "0")

    def test_monthly_totals_use_statement_total_per_closing_month_not_created_at(self):
        """Chart bucket for a month is statement.total_amount for period_end in that month."""
        fi_feb = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"%PDF", name="st_feb.pdf"),
            original_filename="st_feb.pdf",
            status=ImportStatus.COMPLETED,
        )
        fi_mar = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"%PDF", name="st_mar.pdf"),
            original_filename="st_mar.pdf",
            status=ImportStatus.COMPLETED,
        )
        VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi_feb,
            period_start=date(2026, 1, 24),
            period_end=date(2026, 2, 23),
            total_amount=Decimal("10.00"),
        )
        VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi_mar,
            period_start=date(2026, 2, 24),
            period_end=date(2026, 3, 23),
            total_amount=Decimal("25.50"),
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"year": "2026", "month": "3"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        totals = {
            f"{t['year']}-{t['month']}": t["total"]
            for t in response.data["monthly_totals"]
        }
        self.assertEqual(totals["2026-2"], "10.00")
        self.assertEqual(totals["2026-3"], "25.50")
