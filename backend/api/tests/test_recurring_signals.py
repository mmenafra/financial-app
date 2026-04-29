"""Tests for recurring-pattern post_save backfill on existing transactions."""

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

User = get_user_model()


class RecurringPatternSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sig-user",
            email="sig@example.com",
            password="StrongPass123!",
        )
        self.cat = Category.objects.create(name="Subs", user=self.user)

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
            category=self.cat,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )

        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.id)

    def test_frequency_only_patch_does_not_recompute(self):
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
            external_id="ext-freq-x",
            status=TransactionStatus.CONFIRMED,
            matched_recurring_pattern=pat,
        )

        pat.frequency = Frequency.YEARLY
        pat.save(update_fields=["frequency", "updated_at"])

        tx.refresh_from_db()
        self.assertEqual(tx.matched_recurring_pattern_id, pat.id)
