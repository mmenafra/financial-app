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

    @patch("api.views.parse_visa_nacional_statement_pdf")
    def test_success_returns_transactions_json(self, mock_parse):
        mock_parse.return_value = {
            "transactions": [
                {
                    "operation_date": "2026-03-06",
                    "posting_code": "0903",
                    "reference_code": "08128021",
                    "description": "TEST",
                    "amount": "100.00",
                }
            ]
        }
        self.client.force_authenticate(user=self.user)
        pdf = SimpleUploadedFile(
            "stmt.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )
        response = self.client.post(self.url, {"file": pdf}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["transactions"]), 1)
        self.assertEqual(response.data["transactions"][0]["reference_code"], "08128021")
        mock_parse.assert_called_once()
