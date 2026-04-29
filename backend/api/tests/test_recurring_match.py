"""Tests for recurring pattern substring matcher."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.models import (
    Category,
    Direction,
    Frequency,
    RecurringPattern,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from api.recurring_match import (
    apply_recurring_match_if_missing,
    match_recurring_pattern_for_description,
    refresh_matched_recurring_from_patterns,
)

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

    def test_apply_recurring_sets_when_missing(self):
        pat = RecurringPattern.objects.create(
            user=self.user,
            category=self.cat,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        tx = Transaction.objects.create(
            user=self.user,
            description="NETFLIX.COM",
            amount=Decimal("10.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id="ext-apply-1",
            status=TransactionStatus.CONFIRMED,
        )
        apply_recurring_match_if_missing(self.user, tx.pk)
        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.pk)

    def test_apply_recurring_does_not_overwrite_existing(self):
        short = RecurringPattern.objects.create(
            user=self.user,
            category=self.cat,
            description_pattern="NET",
            frequency=Frequency.MONTHLY,
        )
        RecurringPattern.objects.create(
            user=self.user,
            category=self.cat,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        tx = Transaction.objects.create(
            user=self.user,
            description="NETFLIX.COM",
            amount=Decimal("10.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id="ext-apply-2",
            status=TransactionStatus.CONFIRMED,
            matched_recurring_pattern=short,
        )
        apply_recurring_match_if_missing(self.user, tx.pk)
        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, short.pk)

    def test_refresh_recomputes_best_pattern(self):
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
        tx = Transaction.objects.create(
            user=self.user,
            description="NETFLIX.COM",
            amount=Decimal("10.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id="ext-refresh-1",
            status=TransactionStatus.CONFIRMED,
            matched_recurring_pattern_id=None,
        )
        refresh_matched_recurring_from_patterns(self.user, tx.pk)
        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, longer.pk)

        longest = RecurringPattern.objects.create(
            user=self.user,
            category=self.cat,
            description_pattern="NETFLIX.COM",
            frequency=Frequency.MONTHLY,
        )
        refresh_matched_recurring_from_patterns(self.user, tx.pk)
        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, longest.pk)
