"""Tests for recurring-pattern post_save backfill on existing transactions."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.models import (
    Direction,
    Frequency,
    RecurringMatchType,
    RecurringPattern,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)

User = get_user_model()


class RecurringPatternSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sig-user",
            email="sig@example.com",
            password="StrongPass123!",
        )

    def test_new_pattern_sets_matched_recurring_on_existing_transaction(self):
        tx = Transaction.objects.create(
            user=self.user,
            description="NETFLIX.COM 844-5052993",
            amount=Decimal("16.15"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id="000000001498572431",
            status=TransactionStatus.CONFIRMED,
        )
        self.assertIsNone(tx.matched_recurring_pattern_id)

        pat = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )

        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.id)

    def test_new_pattern_matches_external_name_when_description_renamed(self):
        tx = Transaction.objects.create(
            user=self.user,
            description="NETFLIX.COM 844-5052993",
            amount=Decimal("16.15"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id="000000001498572432",
            status=TransactionStatus.CONFIRMED,
        )
        Transaction.objects.filter(pk=tx.pk).update(
            description="Streaming — personal",
        )
        tx.refresh_from_db()
        self.assertIn("NETFLIX", (tx.external_name or ""))

        pat = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.id)

    def test_match_type_change_from_partial_to_exact_clears_nonexact_match(self):
        pat = RecurringPattern.objects.create(
            user=self.user,
            description_pattern="NETFLIX.COM",
            frequency=Frequency.MONTHLY,
            match_type=RecurringMatchType.PARTIAL,
        )
        tx = Transaction.objects.create(
            user=self.user,
            description="NETFLIX.COM EXTRA TEXT",
            amount=Decimal("10.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id="ext-exact-switch",
            status=TransactionStatus.CONFIRMED,
            matched_recurring_pattern=pat,
        )
        pat.match_type = RecurringMatchType.EXACT
        pat.save(update_fields=["match_type", "updated_at"])
        tx.refresh_from_db()
        self.assertIsNone(tx.matched_recurring_pattern_id)

    def test_frequency_only_patch_does_not_recompute(self):
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
            external_id="ext-freq-x",
            status=TransactionStatus.CONFIRMED,
            matched_recurring_pattern=pat,
        )

        pat.frequency = Frequency.YEARLY
        pat.save(update_fields=["frequency", "updated_at"])

        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.id)
