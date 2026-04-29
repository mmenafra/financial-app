from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.models import (
    Category,
    FileImport,
    RecurringPattern,
    Transaction,
    VisaInternationalStatement,
    VisaNacionalStatement,
)

User = get_user_model()

_DEFAULT_SINCE_DATE = date(2026, 2, 1)


class Command(BaseCommand):
    help = (
        "Clean DB data: all rows, all data for a user, transactions only, "
        "or a user's data from a cutoff date onward (imports use created_at as operational date)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Delete ALL rows from Transaction, Category, RecurringPattern, FileImport, "
            "VisaInternationalStatement, VisaNacionalStatement, and User tables.",
        )
        parser.add_argument(
            "--user",
            metavar="USERNAME",
            help="Delete all finance data (transactions, categories, recurring patterns) for this user.",
        )
        parser.add_argument(
            "--transactions",
            metavar="USERNAME",
            help="Delete only transactions for this user.",
        )
        parser.add_argument(
            "--user-since",
            metavar="USERNAME",
            dest="user_since",
            help=f"Delete this user's transactions with created_at on/after --from-date (default "
            f"{_DEFAULT_SINCE_DATE.isoformat()}), Visa Intl statements with period_end on/after "
            "that date, FileImport rows with created_at on/after that instant, and all recurring "
            "patterns for this user. Categories are not removed.",
        )
        parser.add_argument(
            "--from-date",
            metavar="YYYY-MM-DD",
            dest="from_date",
            default=None,
            help=f"Cutoff date for --user-since (default {_DEFAULT_SINCE_DATE.isoformat()}).",
        )

    def handle(self, *args, **options):
        modes = (
            options["all"],
            bool(options["user"]),
            bool(options["transactions"]),
            bool(options["user_since"]),
        )
        if sum(modes) != 1:
            raise CommandError(
                "Specify exactly one of: --all, --user <username>, --transactions <username>, "
                "--user-since <username> [--from-date YYYY-MM-DD]"
            )

        if options["all"]:
            self._clean_all()
        elif options["user"]:
            self._clean_user(options["user"])
        elif options["transactions"]:
            self._clean_transactions(options["transactions"])
        else:
            if options["from_date"]:
                try:
                    cutoff = date.fromisoformat(options["from_date"])
                except ValueError as exc:
                    raise CommandError(
                        f"Invalid --from-date {options['from_date']!r}; use YYYY-MM-DD."
                    ) from exc
            else:
                cutoff = _DEFAULT_SINCE_DATE
            self._clean_user_since(options["user_since"], cutoff)

    def _clean_all(self):
        tx_count, _ = Transaction.objects.all().delete()
        rp_count, _ = RecurringPattern.objects.all().delete()
        cat_count, _ = Category.objects.all().delete()
        visa_intl_count, _ = VisaInternationalStatement.objects.all().delete()
        visa_nac_count, _ = VisaNacionalStatement.objects.all().delete()
        fi_count, _ = FileImport.objects.all().delete()
        user_count, _ = User.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {tx_count} transactions, {rp_count} recurring patterns, "
                f"{cat_count} categories, {visa_intl_count} visa international statements, "
                f"{visa_nac_count} visa nacional statements, "
                f"{fi_count} file imports, {user_count} users."
            )
        )

    def _get_user(self, username):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{username}' not found.") from exc

    def _clean_user(self, username):
        user = self._get_user(username)
        tx_count, _ = Transaction.objects.filter(user=user).delete()
        cat_count, _ = Category.objects.filter(user=user).delete()
        rp_count, _ = RecurringPattern.objects.filter(user=user).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {tx_count} transactions, {cat_count} categories, "
                f"{rp_count} recurring patterns for user '{username}'."
            )
        )

    def _clean_transactions(self, username):
        user = self._get_user(username)
        tx_count, _ = Transaction.objects.filter(user=user).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {tx_count} transactions for user '{username}'."
            )
        )

    def _clean_user_since(self, username, cutoff_date: date):
        user = self._get_user(username)
        cutoff_dt = timezone.make_aware(datetime.combine(cutoff_date, datetime.min.time()))

        tx_count, _ = Transaction.objects.filter(
            user=user,
            created_at__gte=cutoff_dt,
        ).delete()
        visa_intl_count, _ = VisaInternationalStatement.objects.filter(
            user=user,
            period_end__gte=cutoff_date,
        ).delete()
        visa_nac_count, _ = VisaNacionalStatement.objects.filter(
            user=user,
            period_end__gte=cutoff_date,
        ).delete()
        fi_count, _ = FileImport.objects.filter(
            user=user,
            created_at__gte=cutoff_dt,
        ).delete()
        rp_count, _ = RecurringPattern.objects.filter(user=user).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"From {cutoff_date.isoformat()} onward for user '{username}': deleted "
                f"{tx_count} transactions, {visa_intl_count} visa international statements, "
                f"{visa_nac_count} visa nacional statements, "
                f"{fi_count} file imports, {rp_count} recurring patterns (categories unchanged)."
            )
        )
