"""Tests for clean_db management command."""

from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from api.models import (
    Category,
    Direction,
    FileImport,
    Frequency,
    ImportStatus,
    RecurringPattern,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
    VisaInternationalStatement,
    VisaNacionalStatement,
)

User = get_user_model()


class CleanDbUserFullTests(TestCase):
    """``--user`` wipes the same finance tables as ``--all`` except the User row."""

    def test_user_deletes_transactions_imports_and_visa_statements(self):
        user = User.objects.create_user(
            username="full-clean-user",
            email="fullclean@example.com",
            password="StrongPass123!",
        )
        fi_intl = FileImport.objects.create(
            user=user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"a", name="intl.pdf"),
            original_filename="intl.pdf",
            status=ImportStatus.COMPLETED,
        )
        VisaInternationalStatement.objects.create(
            user=user,
            file_import=fi_intl,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            total_amount=Decimal("100.00"),
        )
        fi_nac = FileImport.objects.create(
            user=user,
            source=Source.CREDIT_CARD_NATIONAL,
            file=ContentFile(b"b", name="nac.pdf"),
            original_filename="nac.pdf",
            status=ImportStatus.COMPLETED,
        )
        VisaNacionalStatement.objects.create(
            user=user,
            file_import=fi_nac,
            period_end=date(2026, 2, 28),
            total_amount=Decimal("50000.00"),
        )
        Transaction.objects.create(
            user=user,
            description="Row",
            amount=Decimal("1.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
        )

        call_command("clean_db", "--user", user.username)

        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(Transaction.objects.filter(user=user).exists())
        self.assertFalse(FileImport.objects.filter(user=user).exists())
        self.assertFalse(VisaInternationalStatement.objects.filter(user=user).exists())
        self.assertFalse(VisaNacionalStatement.objects.filter(user=user).exists())


class CleanDbUserSinceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="clean-user",
            email="clean@example.com",
            password="StrongPass123!",
        )

    def test_user_since_removes_transactions_on_or_after_cutoff(self):
        jan = timezone.make_aware(datetime(2026, 1, 15, 12, 0, 0))
        feb = timezone.make_aware(datetime(2026, 2, 1, 0, 0, 0))
        mar = timezone.make_aware(datetime(2026, 3, 1, 12, 0, 0))

        t_jan = Transaction.objects.create(
            user=self.user,
            description="January",
            amount=Decimal("10.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
        )
        Transaction.objects.filter(pk=t_jan.pk).update(created_at=jan)

        t_feb = Transaction.objects.create(
            user=self.user,
            description="February boundary",
            amount=Decimal("20.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
        )
        Transaction.objects.filter(pk=t_feb.pk).update(created_at=feb)

        t_mar = Transaction.objects.create(
            user=self.user,
            description="March",
            amount=Decimal("30.00"),
            currency="USD",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            status=TransactionStatus.CONFIRMED,
        )
        Transaction.objects.filter(pk=t_mar.pk).update(created_at=mar)

        call_command("clean_db", "--user-since", self.user.username, "--from-date", "2026-02-01")

        remaining = set(Transaction.objects.filter(user=self.user).values_list("description", flat=True))
        self.assertEqual(remaining, {"January"})

    def test_user_since_deletes_matching_visa_statements_and_file_imports(self):
        fi_old = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"x", name="old.dat"),
            original_filename="old.dat",
            status=ImportStatus.COMPLETED,
        )
        early = timezone.make_aware(datetime(2026, 1, 10, 8, 0, 0))
        FileImport.objects.filter(pk=fi_old.pk).update(created_at=early)

        VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi_old,
            period_start=early.date(),
            period_end=early.date(),
            total_amount=Decimal("1.00"),
        )

        fi_new = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=ContentFile(b"y", name="new.dat"),
            original_filename="new.dat",
            status=ImportStatus.COMPLETED,
        )
        late = timezone.make_aware(datetime(2026, 2, 5, 8, 0, 0))
        FileImport.objects.filter(pk=fi_new.pk).update(created_at=late)

        VisaInternationalStatement.objects.create(
            user=self.user,
            file_import=fi_new,
            period_start=late.date(),
            period_end=late.date(),
            total_amount=Decimal("2.00"),
        )

        call_command("clean_db", "--user-since", self.user.username, "--from-date", "2026-02-01")

        self.assertEqual(FileImport.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            FileImport.objects.filter(user=self.user).first().pk,
            fi_old.pk,
        )
        self.assertEqual(VisaInternationalStatement.objects.filter(user=self.user).count(), 1)

    def test_user_since_deletes_all_recurring_patterns_keeps_categories(self):
        cat = Category.objects.create(name="Keep me", user=self.user)
        RecurringPattern.objects.create(
            user=self.user,
            category=cat,
            description_pattern="NETFLIX",
            frequency=Frequency.MONTHLY,
        )
        call_command("clean_db", "--user-since", self.user.username, "--from-date", "2026-02-01")
        self.assertFalse(RecurringPattern.objects.filter(user=self.user).exists())
        self.assertTrue(Category.objects.filter(pk=cat.pk).exists())

    def test_requires_exactly_one_mode(self):
        with self.assertRaises(CommandError):
            call_command("clean_db")

        with self.assertRaises(CommandError):
            call_command("clean_db", "--all", "--user", self.user.username)

    def test_invalid_from_date(self):
        with self.assertRaises(CommandError):
            call_command(
                "clean_db",
                "--user-since",
                self.user.username,
                "--from-date",
                "not-a-date",
            )
