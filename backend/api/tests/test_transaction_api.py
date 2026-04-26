from datetime import datetime
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from api.models import (
    Category,
    Direction,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)

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
        self.other_category = Category.objects.create(
            name="Other", user=self.other_user
        )
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

    @staticmethod
    def _create_tx(
        user,
        *,
        description="X",
        source=Source.BANK_ACCOUNT,
        category=None,
    ):
        return Transaction.objects.create(
            user=user,
            description=description,
            amount=Decimal("10.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=source,
            category=category,
            status=TransactionStatus.CONFIRMED,
        )

    def test_list_filter_by_year(self):
        a = self._create_tx(self.user, description="A")
        b = self._create_tx(self.user, description="B")
        Transaction.objects.filter(pk=a.pk).update(
            created_at=timezone.make_aware(datetime(2024, 6, 1, 12, 0, 0))
        )
        Transaction.objects.filter(pk=b.pk).update(
            created_at=timezone.make_aware(datetime(2026, 1, 15, 8, 0, 0))
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url, {"year": 2026})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({row["id"] for row in response.data}, {str(b.id)})

    def test_list_filter_by_year_and_month(self):
        m3 = self._create_tx(self.user, description="March")
        m4 = self._create_tx(self.user, description="April")
        Transaction.objects.filter(pk=m3.pk).update(
            created_at=timezone.make_aware(datetime(2025, 3, 10, 0, 0, 0))
        )
        Transaction.objects.filter(pk=m4.pk).update(
            created_at=timezone.make_aware(datetime(2025, 4, 5, 0, 0, 0))
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.list_url, {"year": 2025, "month": 3}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({row["id"] for row in response.data}, {str(m3.id)})

    def test_list_month_without_year_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url, {"month": 3})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("month", response.data)

    def test_list_filter_by_category(self):
        cat2 = Category.objects.create(name="Food", user=self.user)
        t1 = self._create_tx(self.user, category=self.category)
        t2 = self._create_tx(self.user, category=cat2)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.list_url, {"category": str(self.category.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({row["id"] for row in response.data}, {str(t1.id)})
        self.assertNotIn(str(t2.id), {row["id"] for row in response.data})

    def test_list_filter_by_category_not_owned_returns_400(self):
        self._create_tx(self.user)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.list_url, {"category": str(self.other_category.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_list_filter_by_source(self):
        mp = self._create_tx(
            self.user, source=Source.MERCADOPAGO, description="MP"
        )
        self._create_tx(
            self.user, source=Source.CREDIT_CARD_NATIONAL, description="CC"
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.list_url, {"source": Source.MERCADOPAGO}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({row["id"] for row in response.data}, {str(mp.id)})

    def test_list_invalid_source_returns_400(self):
        self._create_tx(self.user)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url, {"source": "NOT_A_SOURCE"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("source", response.data)

    def test_list_invalid_month_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.list_url, {"year": 2025, "month": 13}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("month", response.data)

    def test_list_combined_year_and_source(self):
        match = self._create_tx(
            self.user, source=Source.MERCADOPAGO, description="ok"
        )
        Transaction.objects.filter(pk=match.pk).update(
            created_at=timezone.make_aware(datetime(2025, 7, 1, 0, 0, 0))
        )
        other = self._create_tx(
            self.user, source=Source.MERCADOPAGO, description="other year"
        )
        Transaction.objects.filter(pk=other.pk).update(
            created_at=timezone.make_aware(datetime(2024, 7, 1, 0, 0, 0))
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.list_url, {"year": 2025, "source": Source.MERCADOPAGO}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({row["id"] for row in response.data}, {str(match.id)})

    def test_retrieve_ignores_list_query_params(self):
        t = self._create_tx(self.user)
        Transaction.objects.filter(pk=t.pk).update(
            created_at=timezone.make_aware(datetime(2026, 3, 1, 0, 0, 0))
        )
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("transaction-detail", args=[t.id])
        response = self.client.get(detail_url, {"year": 1990})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(t.id))
