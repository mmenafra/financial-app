from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.urls import reverse

from api.models import Category

User = get_user_model()


class CategoryAPITests(APITestCase):
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
        self.list_url = reverse("category-list")

    def test_list_requires_authentication(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crud_category_authenticated(self):
        self.client.force_authenticate(user=self.user)
        create_response = self.client.post(
            self.list_url, {"name": "Housing"}, format="json"
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        category_id = create_response.data["id"]

        detail_url = reverse("category-detail", args=[category_id])
        get_response = self.client.get(detail_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["name"], "Housing")

        patch_response = self.client.patch(detail_url, {"icon": "home"}, format="json")
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["icon"], "home")

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(pk=category_id).exists())

    def test_user_only_sees_own_categories(self):
        own = Category.objects.create(name="Own", user=self.user)
        Category.objects.create(name="Other", user=self.other_user)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(own.id))
