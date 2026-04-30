from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

User = get_user_model()


class ImportVisaNationalAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="visa-user",
            email="visa@example.com",
            password="StrongPass123!",
        )
        self.url = reverse("import-visa-national")

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

    @patch("api.import_pipeline.parse_visa_nacional_statement_pdf")
    def test_success_returns_transactions_json(self, mock_parse):
        mock_parse.return_value = {
            "period_end": "2026-03-24",
            "total_operaciones": "340633",
            "transactions": [
                {
                    "operation_date": "2026-03-06",
                    "posting_code": "0903",
                    "reference_code": "08128021",
                    "description": "TEST",
                    "amount": "100.00",
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
        self.assertEqual(response.data["skipped_items"], [])
        self.assertEqual(len(response.data["transactions"]), 1)
        self.assertEqual(response.data["transactions"][0]["external_id"], "08128021:2026-03-06")
        mock_parse.assert_called_once()

    @patch("api.import_pipeline.parse_visa_nacional_statement_pdf")
    def test_pago_en_efectivo_skipped_not_imported(self, mock_parse):
        mock_parse.return_value = {
            "period_end": "2026-03-24",
            "total_operaciones": "340633",
            "transactions": [
                {
                    "operation_date": "2026-03-06",
                    "posting_code": "0903",
                    "reference_code": "08128021",
                    "description": "PAGO EN EFECTIVO",
                    "amount": "50000",
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
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["skipped"], 1)
        self.assertEqual(len(response.data["skipped_items"]), 1)
        self.assertIn(
            "EFECTIVO",
            response.data["skipped_items"][0]["description"].upper(),
        )
        self.assertEqual(len(response.data["transactions"]), 0)

    @patch("api.import_pipeline.parse_visa_nacional_statement_pdf")
    def test_duplicate_reference_populates_skipped_items(self, mock_parse):
        row = {
            "operation_date": "2026-03-06",
            "posting_code": "0903",
            "reference_code": "08128021",
            "description": "DUPE TEST",
            "amount": "100.00",
        }
        mock_parse.return_value = {
            "period_end": "2026-03-24",
            "total_operaciones": "340633",
            "transactions": [row],
        }
        self.client.force_authenticate(user=self.user)
        pdf = SimpleUploadedFile(
            "stmt.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        r1 = self.client.post(self.url, {"file": pdf}, format="multipart")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.data["created"], 1)
        self.assertEqual(r1.data["skipped_items"], [])
        pdf2 = SimpleUploadedFile(
            "stmt2.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        r2 = self.client.post(self.url, {"file": pdf2}, format="multipart")
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.data["created"], 0)
        self.assertEqual(r2.data["skipped"], 1)
        self.assertEqual(len(r2.data["skipped_items"]), 1)
        self.assertEqual(r2.data["skipped_items"][0]["description"], "DUPE TEST")
        self.assertEqual(r2.data["skipped_items"][0]["amount"], "100.00")
        self.assertEqual(r2.data["skipped_items"][0]["currency"], "CLP")

    @patch("api.import_pipeline.parse_visa_nacional_statement_pdf")
    def test_same_reference_different_operation_date_creates_both(self, mock_parse):
        """Bank reference codes can repeat across months; id is reference + operation date."""
        mock_parse.return_value = {
            "period_end": "2026-04-24",
            "total_operaciones": "200",
            "transactions": [
                {
                    "operation_date": "2026-03-06",
                    "posting_code": "0903",
                    "reference_code": "09999999",
                    "description": "ROW A",
                    "amount": "100.00",
                },
                {
                    "operation_date": "2026-04-06",
                    "posting_code": "0903",
                    "reference_code": "09999999",
                    "description": "ROW B",
                    "amount": "100.00",
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
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["skipped"], 0)
        ids = {tx["external_id"] for tx in response.data["transactions"]}
        self.assertEqual(
            ids,
            {"09999999:2026-03-06", "09999999:2026-04-06"},
        )
