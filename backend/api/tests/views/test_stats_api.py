from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.urls import reverse

from api.models import (
    Category,
    Direction,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)

User = get_user_model()


class StatsMonthlyAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="stats-monthly",
            email="stats-month@example.com",
            password="StrongPass123!",
        )
        self.other = User.objects.create_user(
            username="stats-monthly-other",
            email="stats-other@example.com",
            password="StrongPass123!",
        )
        self.cat_a = Category.objects.create(
            user=self.user, name="Food", color="#aa0000"
        )
        self.cat_b = Category.objects.create(
            user=self.user, name="Travel", color="#00aa00"
        )
        self.url = reverse("stats-monthly")

    def test_requires_auth(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_excludes_zero_amount_categories_and_sorts_desc(self):
        Transaction.objects.create(
            user=self.user,
            description="Lunch",
            amount=Decimal("100.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=self.cat_a,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 3, 10),
        )
        Transaction.objects.create(
            user=self.user,
            description="Trip",
            amount=Decimal("50.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=self.cat_b,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 3, 11),
        )
        zero_cat = Category.objects.create(
            user=self.user, name="ZeroCat", color="#0000aa"
        )
        Transaction.objects.create(
            user=self.user,
            description="Nothing",
            amount=Decimal("0.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=zero_cat,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 3, 12),
        )
        Transaction.objects.create(
            user=self.other,
            description="Other",
            amount=Decimal("999.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=self.cat_a,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 3, 1),
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"month": 3, "year": 2025})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["month"], 3)
        self.assertEqual(response.data["year"], 2025)
        self.assertEqual(response.data["total"], "150.00")
        cats = response.data["categories"]
        self.assertEqual(len(cats), 2)
        self.assertEqual(cats[0]["id"], str(self.cat_a.id))
        self.assertEqual(cats[0]["amount"], "100.00")
        self.assertAlmostEqual(cats[0]["percentage"], 66.67, places=1)
        self.assertEqual(cats[1]["id"], str(self.cat_b.id))

    def test_excludes_hidden_from_totals_and_grand_total(self):
        Transaction.objects.create(
            user=self.user,
            description="Visible",
            amount=Decimal("40.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=self.cat_a,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 8, 1),
            is_hidden=False,
        )
        Transaction.objects.create(
            user=self.user,
            description="Hidden",
            amount=Decimal("60.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=self.cat_a,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 8, 2),
            is_hidden=True,
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"month": 8, "year": 2025})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], "40.00")
        self.assertEqual(len(response.data["categories"]), 1)


class StatsTrendAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="stats-trend",
            email="stats-trend@example.com",
            password="StrongPass123!",
        )
        self.cat = Category.objects.create(user=self.user, name="Food", color="#aa0000")
        self.url = reverse("stats-category-trend")

    def test_requires_category_id(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_returns_twelve_month_window(self):
        Transaction.objects.create(
            user=self.user,
            description="May spend",
            amount=Decimal("120.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=self.cat,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 5, 5),
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.url,
            {
                "category_id": str(self.cat.id),
                "reference_month": 5,
                "reference_year": 2025,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["months"]), 12)
        self.assertEqual(len(response.data["totals"]), 12)
        self.assertEqual(response.data["months"][0], "2024-06")
        self.assertEqual(response.data["months"][-1], "2025-05")
        self.assertEqual(response.data["totals"][-1], "120.00")

    def test_excludes_hidden_from_category_trend_totals(self):
        Transaction.objects.create(
            user=self.user,
            description="Vis",
            amount=Decimal("10.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=self.cat,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 5, 5),
            is_hidden=False,
        )
        Transaction.objects.create(
            user=self.user,
            description="Hid",
            amount=Decimal("999.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=self.cat,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2025, 5, 6),
            is_hidden=True,
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.url,
            {
                "category_id": str(self.cat.id),
                "reference_month": 5,
                "reference_year": 2025,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totals"][-1], "10.00")

    def test_category_not_found(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.url,
            {
                "category_id": "00000000-0000-0000-0000-000000000099",
                "reference_month": 1,
                "reference_year": 2025,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
