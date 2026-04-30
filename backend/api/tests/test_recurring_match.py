"""Tests for recurring pattern substring matcher."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.models import (
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
    recurring_match_haystack,
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
        RecurringPattern.objects.create(
            user=self.other,
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
            description_pattern="NET",
            frequency=Frequency.MONTHLY,
        )
        longer = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        found = match_recurring_pattern_for_description(
            self.user,
            "NETFLIX.COM",
        )
        self.assertEqual(found.pk, longer.pk)

    def test_recurring_match_haystack_prefers_external_name(self):
        self.assertEqual(
            recurring_match_haystack("  NETFLIX.COM  ", "User renamed"),
            "NETFLIX.COM",
        )

    def test_recurring_match_haystack_falls_back_to_description(self):
        self.assertEqual(
            recurring_match_haystack(None, "NETFLIX.COM"),
            "NETFLIX.COM",
        )
        self.assertEqual(recurring_match_haystack("", "NETFLIX.COM"), "NETFLIX.COM")
        self.assertEqual(recurring_match_haystack("   ", "NETFLIX.COM"), "NETFLIX.COM")

    def test_apply_uses_external_name_when_description_differs(self):
        pat = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        tx = Transaction.objects.create(
            user=self.user,
            description="My streaming (renamed)",
            amount=Decimal("10.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id="ext-apply-extname",
            status=TransactionStatus.CONFIRMED,
        )
        Transaction.objects.filter(pk=tx.pk).update(
            external_name="NETFLIX.COM 844-5052993",
        )
        apply_recurring_match_if_missing(self.user, tx.pk)
        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.pk)

    def test_apply_falls_back_to_description_when_external_name_empty(self):
        pat = RecurringPattern.objects.create(
            user=self.user,
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
            external_id="ext-apply-legacy",
            status=TransactionStatus.CONFIRMED,
        )
        Transaction.objects.filter(pk=tx.pk).update(external_name="")
        apply_recurring_match_if_missing(self.user, tx.pk)
        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.pk)

    def test_apply_recurring_sets_when_missing(self):
        pat = RecurringPattern.objects.create(
            user=self.user,
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
            description_pattern="NET",
            frequency=Frequency.MONTHLY,
        )
        RecurringPattern.objects.create(
            user=self.user,
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
            description_pattern="NET",
            frequency=Frequency.MONTHLY,
        )
        longer = RecurringPattern.objects.create(
            user=self.user,
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
            description_pattern="NETFLIX.COM",
            frequency=Frequency.MONTHLY,
        )
        refresh_matched_recurring_from_patterns(self.user, tx.pk)
        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, longest.pk)
