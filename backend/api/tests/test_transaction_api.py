from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Category, Direction, Source, Transaction, TransactionStatus, TransactionType

User = get_user_model()


class TransactionAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tester",
            email="tester@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other-tester",
            email="other@example.com",
            password="StrongPass123!",
        )
        self.category = Category.objects.create(name="Transport", user=self.user)
        self.other_category = Category.objects.create(name="Other", user=self.other_user)
        self.list_url = reverse("transaction-list")
        self.payload = {
            "description": "Uber",
            "amount": "15.50",
            "currency": "CLP",
            "transaction_type": TransactionType.DEBIT,
            "direction": Direction.EXPENSE,
            "category": str(self.category.id),
            "source": Source.MERCADOPAGO,
            "status": TransactionStatus.CONFIRMED,
        }

    def test_list_requires_authentication(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crud_transaction_authenticated(self):
        self.client.force_authenticate(user=self.user)
        create_response = self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        transaction_id = create_response.data["id"]

        detail_url = reverse("transaction-detail", args=[transaction_id])
        get_response = self.client.get(detail_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["description"], "Uber")

        patch_response = self.client.patch(
            detail_url,
            {"description": "Uber Black", "amount": "22.00"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["description"], "Uber Black")
        self.assertEqual(Decimal(patch_response.data["amount"]), Decimal("22.00"))

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Transaction.objects.filter(pk=transaction_id).exists())

    def test_user_only_sees_own_transactions(self):
        own = Transaction.objects.create(
            user=self.user,
            description="Own",
            amount=Decimal("10.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
        )
        Transaction.objects.create(
            user=self.other_user,
            description="Other",
            amount=Decimal("20.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(own.id))

    def test_cannot_create_transaction_with_other_users_category(self):
        self.client.force_authenticate(user=self.user)
        payload = dict(self.payload)
        payload["category"] = str(self.other_category.id)

        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
