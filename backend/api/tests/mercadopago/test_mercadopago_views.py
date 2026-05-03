from decimal import Decimal
from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import (
    Direction,
    MercadoPagoStoredPayment,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)

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

    def test_stored_payment_detail_returns_payload_for_owner(self):
        self.client.force_authenticate(user=self.user)
        row = MercadoPagoStoredPayment.objects.create(
            user=self.user,
            mp_payment_id=42,
            synced_at=timezone.now(),
            payload={"id": 42, "status": "approved"},
        )
        url = reverse("mercadopago-stored-payment-detail", args=[row.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], 42)

    def test_stored_payment_detail_404_for_other_user(self):
        other = User.objects.create_user(
            username="other-mp",
            email="o@example.com",
            password="StrongPass123!",
        )
        row = MercadoPagoStoredPayment.objects.create(
            user=other,
            mp_payment_id=99,
            synced_at=timezone.now(),
            payload={"id": 99},
        )
        self.client.force_authenticate(user=self.user)
        url = reverse("mercadopago-stored-payment-detail", args=[row.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(MERCADOPAGO_ACCESS_TOKEN="APP_USR-test-token")
class MercadoPagoStoredPaymentLinkAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mp-link-user",
            email="link@example.com",
            password="StrongPass123!",
        )
        self.link_url = reverse("mercadopago-stored-payment-link")
        self.vn_tx = Transaction.objects.create(
            user=self.user,
            description="MERCADOPAGO *MANUAL",
            amount=Decimal("19990.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_NATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=timezone.now().date(),
        )

    def test_link_requires_authentication(self):
        response = self.client.post(
            self.link_url,
            {"mp_payment_id": 1, "transaction_id": str(self.vn_tx.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @mock.patch("api.mercadopago.views.get_payment")
    def test_link_success(self, mock_get_payment):
        mock_get_payment.return_value = {
            "status": 200,
            "response": {
                "id": 90001,
                "currency_id": "CLP",
                "description": "ML purchase",
                "transaction_amount": 19990,
            },
        }
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.link_url,
            {"mp_payment_id": 90001, "transaction_id": str(self.vn_tx.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mp_payment_id"], 90001)
        self.assertEqual(response.data["transaction_id"], str(self.vn_tx.pk))
        sp = MercadoPagoStoredPayment.objects.get(mp_payment_id=90001)
        self.assertEqual(sp.visa_transaction_id, self.vn_tx.pk)
        self.assertEqual(str(sp.pk), response.data["stored_payment_id"])

    @mock.patch("api.mercadopago.views.get_payment")
    def test_link_clears_other_stored_row_for_same_transaction(self, mock_get_payment):
        old_sp = MercadoPagoStoredPayment.objects.create(
            user=self.user,
            mp_payment_id=80001,
            synced_at=timezone.now(),
            payload={"id": 80001, "currency_id": "CLP"},
            visa_transaction=self.vn_tx,
        )
        mock_get_payment.return_value = {
            "status": 200,
            "response": {
                "id": 90002,
                "currency_id": "CLP",
                "transaction_amount": 19990,
            },
        }
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.link_url,
            {"mp_payment_id": 90002, "transaction_id": str(self.vn_tx.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        old_sp.refresh_from_db()
        self.assertIsNone(old_sp.visa_transaction_id)
        new_sp = MercadoPagoStoredPayment.objects.get(mp_payment_id=90002)
        self.assertEqual(new_sp.visa_transaction_id, self.vn_tx.pk)

    @mock.patch("api.mercadopago.views.get_payment")
    def test_link_rejects_non_nacional_source(self, mock_get_payment):
        other = Transaction.objects.create(
            user=self.user,
            description="Bank row",
            amount=Decimal("100.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
            transaction_date=timezone.now().date(),
        )
        mock_get_payment.return_value = {
            "status": 200,
            "response": {"id": 1, "currency_id": "CLP"},
        }
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.link_url,
            {"mp_payment_id": 1, "transaction_id": str(other.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_get_payment.assert_not_called()

    def test_link_rejects_non_clp_transaction(self):
        usd_tx = Transaction.objects.create(
            user=self.user,
            description="USD row",
            amount=Decimal("10.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_NATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=timezone.now().date(),
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.link_url,
            {"mp_payment_id": 1, "transaction_id": str(usd_tx.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch("api.mercadopago.views.get_payment")
    def test_link_rejects_non_clp_payment(self, mock_get_payment):
        mock_get_payment.return_value = {
            "status": 200,
            "response": {"id": 12, "currency_id": "USD"},
        }
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.link_url,
            {"mp_payment_id": 12, "transaction_id": str(self.vn_tx.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch("api.mercadopago.views.get_payment")
    def test_link_rejects_split_bundle(self, mock_get_payment):
        bundle = Transaction.objects.create(
            user=self.user,
            description="Bundle",
            amount=Decimal("500.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_NATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=timezone.now().date(),
        )
        Transaction.objects.create(
            user=self.user,
            description="Child",
            amount=Decimal("500.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_NATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=timezone.now().date(),
            parent=bundle,
        )
        mock_get_payment.return_value = {
            "status": 200,
            "response": {"id": 77, "currency_id": "CLP"},
        }
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.link_url,
            {"mp_payment_id": 77, "transaction_id": str(bundle.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_get_payment.assert_not_called()

    def test_link_missing_token_returns_503(self):
        user = User.objects.create_user(
            username="mp-link-no-tok",
            email="nt@example.com",
            password="StrongPass123!",
        )
        tx = Transaction.objects.create(
            user=user,
            description="VN",
            amount=Decimal("1.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_NATIONAL,
            status=TransactionStatus.CONFIRMED,
            transaction_date=timezone.now().date(),
        )
        with override_settings(MERCADOPAGO_ACCESS_TOKEN=""):
            self.client.force_authenticate(user=user)
            response = self.client.post(
                reverse("mercadopago-stored-payment-link"),
                {"mp_payment_id": 1, "transaction_id": str(tx.pk)},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
