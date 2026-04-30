from datetime import date
from decimal import Decimal
from urllib.parse import urlparse

from rest_framework import status
from rest_framework.test import APITestCase

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

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
        Transaction.objects.filter(pk=tx.pk).update(transaction_date=date(2026, 3, 15))

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"year": "2026", "month": "3"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.data
        self.assertIsNotNone(body["statement"])
        self.assertEqual(str(body["statement"]["id"]), str(stmt.id))
        self.assertEqual(body["statement"]["period_end"], "2026-03-23")
        self.assertEqual(body["statement"]["original_filename"], "st.pdf")
        self.assertIn(
            "/media/",
            body["statement"]["uploaded_file_url"],
        )
        self.assertEqual(len(body["transactions"]), 1)
        self.assertEqual(len(body["monthly_totals"]), 12)
        last = body["monthly_totals"][-1]
        self.assertEqual(last["year"], 2026)
        self.assertEqual(last["month"], 3)
        self.assertEqual(last["total"], "16.15")

        # Ensure project urls.py exposes MEDIA_ROOT under MEDIA_URL when DEBUG=True
        # (browser / new-tab links rely on GET /media/...).
        if settings.DEBUG:
            media_path = urlparse(body["statement"]["uploaded_file_url"]).path
            media_resp = self.client.get(media_path)
            self.assertEqual(media_resp.status_code, status.HTTP_200_OK)
            self.assertGreater(len(media_resp.content), 0)

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
        Transaction.objects.filter(pk=tx.pk).update(transaction_date=date(2020, 1, 15))
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

    def test_duplicate_period_statements_prefers_row_with_transactions(self):
        fi_empty = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"%PDF", name="dup_empty.pdf"),
            original_filename="dup_empty.pdf",
            status=ImportStatus.COMPLETED,
        )
        fi_with_tx = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"%PDF", name="dup_tx.pdf"),
            original_filename="dup_tx.pdf",
            status=ImportStatus.COMPLETED,
        )
        VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi_empty,
            period_start=date(2026, 2, 24),
            period_end=date(2026, 3, 23),
            total_amount=Decimal("69.27"),
        )
        stmt_with_tx = VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi_with_tx,
            period_start=date(2026, 2, 24),
            period_end=date(2026, 3, 23),
            total_amount=Decimal("69.27"),
        )
        Transaction.objects.create(
            user=self.user,
            description="NETFLIX",
            amount=Decimal("16.15"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
            visa_international_statement=stmt_with_tx,
            external_id="dup-pref-001",
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"year": "2026", "month": "3"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["statement"])
        self.assertEqual(
            response.data["statement"]["id"], str(stmt_with_tx.id)
        )
        self.assertEqual(len(response.data["transactions"]), 1)
