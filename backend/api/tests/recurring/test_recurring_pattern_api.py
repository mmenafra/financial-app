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
        self.assertEqual(create_response.data["match_type"], "PARTIAL")

        detail_url = reverse("recurring-pattern-detail", args=[pattern_id])
        get_response = self.client.get(detail_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["description_pattern"], "netflix")

        patch_response = self.client.patch(
            detail_url,
            {"frequency": Frequency.YEARLY, "match_type": "EXACT"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["frequency"], Frequency.YEARLY)
        self.assertEqual(patch_response.data["match_type"], "EXACT")

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RecurringPattern.objects.filter(pk=pattern_id).exists())

    def test_duplicate_create_returns_400(self):
        self.client.force_authenticate(user=self.user)
        r1 = self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("match text", str(r2.data).lower())

    def test_duplicate_after_normalize_returns_400(self):
        self.client.force_authenticate(user=self.user)
        r1 = self.client.post(
            self.list_url,
            {**self.payload, "description_pattern": "NETFLIX"},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.client.post(
            self.list_url,
            {**self.payload, "description_pattern": "netflix"},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_to_colliding_pattern_returns_400(self):
        self.client.force_authenticate(user=self.user)
        a = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="alpha",
            frequency=Frequency.MONTHLY,
        )
        b = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="bravo",
            frequency=Frequency.MONTHLY,
        )
        url_b = reverse("recurring-pattern-detail", args=[b.id])
        resp = self.client.patch(
            url_b,
            {"description_pattern": "ALPHA"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.description_pattern, "alpha")
        self.assertEqual(b.description_pattern, "bravo")

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
