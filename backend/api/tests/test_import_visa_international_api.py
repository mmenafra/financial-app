import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.signals import post_save
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    Category,
    Frequency,
    RecurringPattern,
    Source,
    Transaction,
    VisaInternationalStatement,
)
from api.recurring_signals import _recurring_pattern_refresh_matching_transactions

User = get_user_model()


class ImportVisaInternationalAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="visa-intl-user",
            email="visa-intl@example.com",
            password="StrongPass123!",
        )
        self.url = reverse("import-visa-international")

    def test_endpoint_requires_authentication(self):
        pdf = SimpleUploadedFile(
            "stmt.pdf",
            b"%PDF-1.4 fake",
            content_type="application/pdf",
        )
        response = self.client.post(self.url, {"file": pdf}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_file_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data["detail"].lower())

    def test_only_pdf_files_are_supported(self):
        self.client.force_authenticate(user=self.user)
        bad = SimpleUploadedFile(
            "stmt.dat",
            b"x",
            content_type="application/octet-stream",
        )
        response = self.client.post(self.url, {"file": bad}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Only .pdf files are supported.")

    @patch("api.import_pipeline.parse_visa_internacional_statement_pdf")
    def test_success_returns_transactions_json(self, mock_parse):
        mock_parse.return_value = {
            "period_from": "2026-02-24",
            "period_to": "2026-03-23",
            "transactions": [
                {
                    "reference": "000000001498572431",
                    "operation_date": "2026-02-25",
                    "description": "NETFLIX.COM 844-5052993",
                    "city": None,
                    "country": "CA",
                    "amount_local": "21.46",
                    "amount_usd": "16.15",
                }
            ],
        }
        self.client.force_authenticate(user=self.user)
        pdf = SimpleUploadedFile(
            "stmt.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        response = self.client.post(self.url, {"file": pdf}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(response.data["skipped"], 0)
        self.assertEqual(len(response.data["transactions"]), 1)
        tx0 = response.data["transactions"][0]
        self.assertEqual(tx0["external_id"], "000000001498572431")
        self.assertEqual(tx0["description"], "NETFLIX.COM 844-5052993")
        self.assertEqual(tx0["amount"], "16.15")
        self.assertEqual(tx0["currency"], "USD")
        stmt = VisaInternationalStatement.objects.get()
        self.assertEqual(stmt.period_start.isoformat(), "2026-02-24")
        self.assertEqual(stmt.period_end.isoformat(), "2026-03-23")
        self.assertEqual(stmt.total_amount, Decimal("16.15"))
        self.assertEqual(str(stmt.id), str(tx0["visa_international_statement"]))
        tx = Transaction.objects.get(pk=tx0["id"])
        self.assertEqual(tx.visa_international_statement_id, stmt.id)
        mock_parse.assert_called_once()

    @patch("api.import_pipeline.parse_visa_internacional_statement_pdf")
    def test_reimport_same_period_reuses_single_statement_row(self, mock_parse):
        """Same statement period does not insert a second VisaInternationalStatement."""
        parsed = {
            "period_from": "2026-02-24",
            "period_to": "2026-03-23",
            "transactions": [
                {
                    "reference": "000000001498572431",
                    "operation_date": "2026-02-25",
                    "description": "NETFLIX.COM 844-5052993",
                    "city": None,
                    "country": "CA",
                    "amount_local": "21.46",
                    "amount_usd": "16.15",
                }
            ],
        }
        mock_parse.return_value = parsed
        self.client.force_authenticate(user=self.user)

        pdf1 = SimpleUploadedFile(
            "stmt1.pdf", b"%PDF-1.4", content_type="application/pdf"
        )
        r1 = self.client.post(self.url, {"file": pdf1}, format="multipart")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        stmt_id = VisaInternationalStatement.objects.get().pk

        pdf2 = SimpleUploadedFile(
            "stmt2.pdf", b"%PDF-1.4", content_type="application/pdf"
        )
        r2 = self.client.post(self.url, {"file": pdf2}, format="multipart")
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)

        self.assertEqual(VisaInternationalStatement.objects.count(), 1)
        self.assertEqual(VisaInternationalStatement.objects.get().pk, stmt_id)

    @patch("api.import_pipeline.parse_visa_internacional_statement_pdf")
    def test_reimport_preferred_id_drifting_period_updates_same_statement_row(
        self, mock_parse,
    ):
        """Reuse by id when parsed period differs (would bypass exact period match)."""
        first_parse = {
            "period_from": "2026-02-24",
            "period_to": "2026-03-23",
            "transactions": [
                {
                    "reference": "000000001498572431",
                    "operation_date": "2026-02-25",
                    "description": "NETFLIX.COM",
                    "city": None,
                    "country": "CA",
                    "amount_local": "21.46",
                    "amount_usd": "16.15",
                }
            ],
        }
        drift_parse = {
            **first_parse,
            "period_from": "2026-02-25",
        }
        self.client.force_authenticate(user=self.user)

        pdf1 = SimpleUploadedFile(
            "stmt1.pdf", b"%PDF-1.4", content_type="application/pdf"
        )
        mock_parse.return_value = first_parse
        r1 = self.client.post(self.url, {"file": pdf1}, format="multipart")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        stmt = VisaInternationalStatement.objects.get()

        pdf2 = SimpleUploadedFile(
            "stmt2.pdf", b"%PDF-1.4", content_type="application/pdf"
        )
        mock_parse.return_value = drift_parse
        r2 = self.client.post(
            self.url,
            {
                "file": pdf2,
                "visa_international_statement_id": str(stmt.pk),
            },
            format="multipart",
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(VisaInternationalStatement.objects.count(), 1)
        stmt.refresh_from_db()
        self.assertEqual(stmt.pk, VisaInternationalStatement.objects.get().pk)
        self.assertEqual(stmt.period_start.isoformat(), drift_parse["period_from"])
        self.assertEqual(stmt.period_end.isoformat(), drift_parse["period_to"])

    def test_invalid_preferred_statement_uuid_returns_400(self):
        self.client.force_authenticate(user=self.user)
        pdf = SimpleUploadedFile(
            "stmt.pdf", b"%PDF-1.4", content_type="application/pdf"
        )
        response = self.client.post(
            self.url,
            {"file": pdf, "visa_international_statement_id": "not-a-uuid"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_preferred_statement_id_returns_400(self):
        self.client.force_authenticate(user=self.user)
        pdf = SimpleUploadedFile(
            "stmt.pdf", b"%PDF-1.4", content_type="application/pdf"
        )
        response = self.client.post(
            self.url,
            {
                "file": pdf,
                "visa_international_statement_id": str(uuid.uuid4()),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("api.import_pipeline.parse_visa_internacional_statement_pdf")
    def test_import_sets_matched_recurring_pattern(self, mock_parse):
        mock_parse.return_value = {
            "period_from": "2026-02-24",
            "period_to": "2026-03-23",
            "transactions": [
                {
                    "reference": "000000001498572431",
                    "operation_date": "2026-02-25",
                    "description": "NETFLIX.COM 844-5052993",
                    "city": None,
                    "country": "CA",
                    "amount_local": "21.46",
                    "amount_usd": "16.15",
                }
            ],
        }
        cat = Category.objects.create(name="Streaming", user=self.user)
        pat = RecurringPattern.objects.create(
            user=self.user,
            category=cat,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        self.client.force_authenticate(user=self.user)
        pdf = SimpleUploadedFile(
            "stmt.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        response = self.client.post(self.url, {"file": pdf}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        tx0 = response.data["transactions"][0]
        self.assertEqual(str(pat.id), str(tx0["matched_recurring_pattern"]))

    @patch("api.import_pipeline.parse_visa_internacional_statement_pdf")
    def test_skipped_duplicate_import_sets_recurring_when_still_missing(
        self, mock_parse,
    ):
        """Re-import skips rows but fills ``matched_recurring_pattern`` if unset."""
        mock_parse.return_value = {
            "period_from": "2026-02-24",
            "period_to": "2026-03-23",
            "transactions": [
                {
                    "reference": "000000001498572431",
                    "operation_date": "2026-02-25",
                    "description": "NETFLIX.COM 844-5052993",
                    "city": None,
                    "country": "CA",
                    "amount_local": "21.46",
                    "amount_usd": "16.15",
                }
            ],
        }
        pdf = SimpleUploadedFile(
            "stmt.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        self.client.force_authenticate(user=self.user)
        self.client.post(self.url, {"file": pdf}, format="multipart")

        tx = Transaction.objects.get(
            external_id="000000001498572431",
            source=Source.CREDIT_CARD_INTERNATIONAL,
        )
        self.assertIsNone(tx.matched_recurring_pattern_id)

        cat = Category.objects.create(name="Streaming", user=self.user)
        # Avoid post_save backfill until the duplicate-import path runs below.
        disconnected = post_save.disconnect(
            receiver=_recurring_pattern_refresh_matching_transactions,
            sender=RecurringPattern,
        )
        self.assertTrue(
            disconnected,
            "failed to detach recurring-pattern post_save handler",
        )
        try:
            pat = RecurringPattern.objects.create(
                user=self.user,
                category=cat,
                description_pattern="NETFLIX",
                frequency=Frequency.MONTHLY,
            )
        finally:
            post_save.connect(
                receiver=_recurring_pattern_refresh_matching_transactions,
                sender=RecurringPattern,
            )

        pdf2 = SimpleUploadedFile(
            "stmt2.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        response = self.client.post(self.url, {"file": pdf2}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["skipped"], 1)
        self.assertEqual(response.data["created"], 0)

        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.id)

    @patch("api.import_pipeline.parse_visa_internacional_statement_pdf")
    def test_pago_en_efectivo_skipped_not_imported_and_excluded_from_statement_total(
        self, mock_parse,
    ):
        mock_parse.return_value = {
            "period_from": "2026-02-24",
            "period_to": "2026-03-23",
            "transactions": [
                {
                    "reference": "111111111111111111",
                    "operation_date": "2026-02-26",
                    "description": "PAGO EN EFECTIVO",
                    "city": None,
                    "country": None,
                    "amount_local": "100.00",
                    "amount_usd": "50.00",
                },
                {
                    "reference": "000000001498572431",
                    "operation_date": "2026-02-25",
                    "description": "NETFLIX.COM 844-5052993",
                    "city": None,
                    "country": "CA",
                    "amount_local": "21.46",
                    "amount_usd": "16.15",
                },
            ],
        }
        self.client.force_authenticate(user=self.user)
        pdf = SimpleUploadedFile(
            "stmt.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        response = self.client.post(self.url, {"file": pdf}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(response.data["skipped"], 1)
        stmt = VisaInternationalStatement.objects.get()
        self.assertEqual(stmt.total_amount, Decimal("16.15"))
