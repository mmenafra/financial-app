from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.urls import reverse

from api.models import (
    Direction,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)

User = get_user_model()


class IncomeAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="income-tester",
            email="income@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other-income",
            email="other-income@example.com",
            password="StrongPass123!",
        )
        self.income_url = reverse("income-list")

    def test_list_requires_authentication(self):
        response = self.client.get(self.income_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_lists_all_income_for_user_without_date_filters(self):
        Transaction.objects.create(
            user=self.user,
            description="Salary",
            amount=Decimal("5000.00"),
            currency="CLP",
            transaction_type=TransactionType.CREDIT,
            direction=Direction.INCOME,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2024, 6, 15),
        )
        Transaction.objects.create(
            user=self.user,
            description="Bonus",
            amount=Decimal("100.00"),
            currency="CLP",
            transaction_type=TransactionType.CREDIT,
            direction=Direction.INCOME,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2023, 1, 1),
        )
        Transaction.objects.create(
            user=self.user,
            description="Coffee",
            amount=Decimal("3.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.MERCADOPAGO,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2024, 6, 10),
        )
        Transaction.objects.create(
            user=self.other_user,
            description="Other salary",
            amount=Decimal("1.00"),
            currency="CLP",
            transaction_type=TransactionType.CREDIT,
            direction=Direction.INCOME,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2024, 6, 12),
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.income_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIn("monthly_totals", response.data)
        self.assertEqual(len(response.data["monthly_totals"]), 12)
        self.assertNotIn("total_income", response.data)

    def test_year_month_filters_list_only_that_period(self):
        Transaction.objects.create(
            user=self.user,
            description="May pay",
            amount=Decimal("100.00"),
            currency="CLP",
            transaction_type=TransactionType.CREDIT,
            direction=Direction.INCOME,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2024, 5, 1),
        )
        Transaction.objects.create(
            user=self.user,
            description="June pay",
            amount=Decimal("200.00"),
            currency="CLP",
            transaction_type=TransactionType.CREDIT,
            direction=Direction.INCOME,
            source=Source.BANK_ACCOUNT,
            status=TransactionStatus.CONFIRMED,
            transaction_date=date(2024, 6, 1),
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            self.income_url, {"year": 2024, "month": 6}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["description"], "June pay")
