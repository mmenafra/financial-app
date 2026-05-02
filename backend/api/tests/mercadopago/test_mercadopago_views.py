from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

User = get_user_model()


@override_settings(MERCADOPAGO_ACCESS_TOKEN="APP_USR-test-token")
class MercadoPagoAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mp-tester",
            email="mp@example.com",
            password="StrongPass123!",
        )
        self.list_url = reverse("mercadopago-transaction-list")

    def test_list_requires_authentication(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @mock.patch("api.mercadopago.views.search_payments")
    def test_list_returns_search_payload(self, mock_search):
        mock_search.return_value = {
            "status": 200,
            "response": {
                "results": [{"id": 123}],
                "paging": {"total": 1, "offset": 0, "limit": 30},
            },
        }
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [{"id": 123}])

    @mock.patch("api.mercadopago.views.search_payments")
    def test_list_forwards_sdk_error_status(self, mock_search):
        mock_search.return_value = {
            "status": 403,
            "response": {"message": "Forbidden"},
        }
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["message"], "Forbidden")

    @mock.patch("api.mercadopago.views.get_payment")
    def test_detail_returns_payment(self, mock_get):
        mock_get.return_value = {
            "status": 200,
            "response": {"id": 999, "status": "approved"},
        }
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("mercadopago-transaction-detail", args=["999"])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], 999)

    def test_missing_token_returns_503(self):
        """When settings token is unset, endpoints report configuration error."""

        user = User.objects.create_user(
            username="mp-empty-token",
            email="empty-tok@example.com",
            password="StrongPass123!",
        )
        with override_settings(MERCADOPAGO_ACCESS_TOKEN=""):
            self.client.force_authenticate(user=user)
            resp_list = self.client.get(self.list_url)
            self.assertEqual(resp_list.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

            detail_url = reverse("mercadopago-transaction-detail", args=["1"])
            resp_detail = self.client.get(detail_url)
            self.assertEqual(
                resp_detail.status_code, status.HTTP_503_SERVICE_UNAVAILABLE
            )
