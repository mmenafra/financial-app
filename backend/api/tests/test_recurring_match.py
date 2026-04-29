"""Tests for recurring pattern substring matcher."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.models import Category, Frequency, RecurringPattern
from api.recurring_match import match_recurring_pattern_for_description

User = get_user_model()


class RecurringMatchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="matcher-user",
            email="matcher@example.com",
            password="StrongPass123!",
        )
        self.other = User.objects.create_user(
            username="other-matcher",
            email="other-matcher@example.com",
            password="StrongPass123!",
        )
        self.cat = Category.objects.create(name="Subs", user=self.user)

    def test_empty_description_returns_none(self):
        self.assertIsNone(
            match_recurring_pattern_for_description(self.user, ""),
        )
        self.assertIsNone(
            match_recurring_pattern_for_description(self.user, "   "),
        )

    def test_no_patterns_returns_none(self):
        self.assertIsNone(
            match_recurring_pattern_for_description(
                self.user,
                "NETFLIX.COM",
            ),
        )

    def test_substring_match_case_insensitive(self):
        RecurringPattern.objects.create(
            user=self.user,
            category=self.cat,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        found = match_recurring_pattern_for_description(
            self.user,
            "NETFLIX.COM 844-5052993",
        )
        self.assertIsNotNone(found)
        self.assertEqual(found.description_pattern, "NETFLIX")

    def test_other_users_patterns_ignored(self):
        oc = Category.objects.create(name="O", user=self.other)
        RecurringPattern.objects.create(
            user=self.other,
            category=oc,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        self.assertIsNone(
            match_recurring_pattern_for_description(
                self.user,
                "NETFLIX.COM",
            ),
        )

    def test_longest_pattern_wins(self):
        RecurringPattern.objects.create(
            user=self.user,
            category=self.cat,
            description_pattern="NET",
            frequency=Frequency.MONTHLY,
        )
        longer = RecurringPattern.objects.create(
            user=self.user,
            category=self.cat,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        found = match_recurring_pattern_for_description(
            self.user,
            "NETFLIX.COM",
        )
        self.assertEqual(found.pk, longer.pk)
