from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.urls import reverse

from api.models import Frequency, RecurringPattern

User = get_user_model()


class RecurringPatternAPITests(APITestCase):
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
        self.list_url = reverse("recurring-pattern-list")
        self.payload = {
            "description_pattern": "NETFLIX",
            "expected_amount": "9.99",
            "frequency": Frequency.MONTHLY,
        }

    def test_list_requires_authentication(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crud_recurring_pattern_authenticated(self):
        self.client.force_authenticate(user=self.user)
        create_response = self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        pattern_id = create_response.data["id"]

        detail_url = reverse("recurring-pattern-detail", args=[pattern_id])
        get_response = self.client.get(detail_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["description_pattern"], "NETFLIX")

        patch_response = self.client.patch(
            detail_url,
            {"frequency": Frequency.YEARLY},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["frequency"], Frequency.YEARLY)

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RecurringPattern.objects.filter(pk=pattern_id).exists())

    def test_user_only_sees_own_recurring_patterns(self):
        own = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="OWN",
            expected_amount="1.00",
            frequency=Frequency.MONTHLY,
        )
        RecurringPattern.objects.create(
            user=self.other_user,
            description_pattern="OTHER",
            expected_amount="2.00",
            frequency=Frequency.MONTHLY,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(own.id))
