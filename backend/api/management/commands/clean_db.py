from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
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
            "VisaInternationalStatement, VisaNacionalStatement, and User tables; clear "
            "django_session; for each FileImport, delete the FileField blob from storage "
            "then delete the row. Social accounts and user profiles cascade with users.",
        )
        parser.add_argument(
            "--user",
            metavar="USERNAME",
            help="Delete all finance data for this user: transactions, Visa Intl/Nacional "
            "statements, file imports, categories, and recurring patterns (user account unchanged).",
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
        tx_count = self._purge_transactions_raw()
        rp_count, _ = RecurringPattern.objects.all().delete()
        cat_count, _ = Category.objects.all().delete()
        visa_intl_count, _ = VisaInternationalStatement.objects.all().delete()
        visa_nac_count, _ = VisaNacionalStatement.objects.all().delete()
        fi_count = self._delete_file_imports_qs(FileImport.objects.all())
        session_count, _ = Session.objects.all().delete()
        user_count, _ = User.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {tx_count} transactions, {rp_count} recurring patterns, "
                f"{cat_count} categories, {visa_intl_count} visa international statements, "
                f"{visa_nac_count} visa nacional statements, "
                f"{fi_count} file imports, {session_count} sessions, {user_count} users."
            )
        )

    def _get_user(self, username):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{username}' not found.") from exc

    def _delete_file_imports_qs(self, queryset) -> int:
        """Remove each FileImport and delete the stored upload from disk.

        Django does not remove FileField blobs when a model instance is deleted.
        QuerySet.delete() uses bulk SQL and skips per-instance behavior entirely.
        """
        pks = list(queryset.values_list("pk", flat=True))
        for pk in pks:
            fi = FileImport.objects.get(pk=pk)
            if fi.file:
                fi.file.delete(save=False)
            fi.delete()
        return len(pks)

    def _purge_transactions_raw(
        self,
        *,
        user_id=None,
        created_at_gte=None,
    ) -> int:
        """DELETE transactions via SQL so this command works if the DB schema lags migrations.

        Avoids ORM ``.delete()`` which SELECTs all model columns (e.g. ``transaction_date``).
        Split rows (``parent_id`` set) are removed in a loop so self-FKs are satisfied
        regardless of database row order.
        """
        conds = []
        params = []
        if user_id is not None:
            conds.append("user_id = %s")
            params.append(user_id)
        if created_at_gte is not None:
            conds.append("created_at >= %s")
            params.append(created_at_gte)
        extra = (" AND " + " AND ".join(conds)) if conds else ""
        where = (" WHERE " + " AND ".join(conds)) if conds else ""

        table = connection.ops.quote_name(Transaction._meta.db_table)
        total = 0
        with connection.cursor() as cursor:
            while True:
                cursor.execute(
                    f"DELETE FROM {table} WHERE parent_id IS NOT NULL{extra}",
                    params,
                )
                n = cursor.rowcount
                total += n
                if n == 0:
                    break
            cursor.execute(f"DELETE FROM {table}{where}", params)
            total += cursor.rowcount
        return total

    def _clean_user(self, username):
        user = self._get_user(username)
        tx_count = self._purge_transactions_raw(user_id=user.pk)
        visa_intl_count, _ = VisaInternationalStatement.objects.filter(
            user=user
        ).delete()
        visa_nac_count, _ = VisaNacionalStatement.objects.filter(user=user).delete()
        fi_count = self._delete_file_imports_qs(FileImport.objects.filter(user=user))
        cat_count, _ = Category.objects.filter(user=user).delete()
        rp_count, _ = RecurringPattern.objects.filter(user=user).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {tx_count} transactions, {visa_intl_count} visa international statements, "
                f"{visa_nac_count} visa nacional statements, {fi_count} file imports, "
                f"{cat_count} categories, {rp_count} recurring patterns for user '{username}'."
            )
        )

    def _clean_transactions(self, username):
        user = self._get_user(username)
        tx_count = self._purge_transactions_raw(user_id=user.pk)
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {tx_count} transactions for user '{username}'."
            )
        )

    def _clean_user_since(self, username, cutoff_date: date):
        user = self._get_user(username)
        cutoff_dt = timezone.make_aware(
            datetime.combine(cutoff_date, datetime.min.time())
        )

        tx_count = self._purge_transactions_since(
            user_id=user.pk,
            created_at_gte=cutoff_dt,
        )
        visa_intl_count, _ = VisaInternationalStatement.objects.filter(
            user=user,
            period_end__gte=cutoff_date,
        ).delete()
        visa_nac_count, _ = VisaNacionalStatement.objects.filter(
            user=user,
            period_end__gte=cutoff_date,
        ).delete()
        fi_count = self._delete_file_imports_qs(
            FileImport.objects.filter(
                user=user,
                created_at__gte=cutoff_dt,
            )
        )
        rp_count, _ = RecurringPattern.objects.filter(user=user).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"From {cutoff_date.isoformat()} onward for user '{username}': deleted "
                f"{tx_count} transactions, {visa_intl_count} visa international statements, "
                f"{visa_nac_count} visa nacional statements, "
                f"{fi_count} file imports, {rp_count} recurring patterns (categories unchanged)."
            )
        )

    def _purge_transactions_since(self, *, user_id, created_at_gte) -> int:
        """Remove transactions with ``created_at`` on/after ``created_at_gte`` via the
        ORM (split rows first). Used for ``--user-since`` so SQLite compares datetimes
        as datetimes; raw ``DELETE ... >= %s`` uses string ordering on SQLite and can
        omit rows at the cutoff instant (e.g. midnight vs ``.000000`` in the bound
        parameter). PostgreSQL is unaffected.
        """
        total = 0
        while True:
            deleted, _ = Transaction.objects.filter(
                user_id=user_id,
                parent_id__isnull=False,
                created_at__gte=created_at_gte,
            ).delete()
            total += deleted
            if deleted == 0:
                break
        deleted, _ = Transaction.objects.filter(
            user_id=user_id,
            created_at__gte=created_at_gte,
        ).delete()
        total += deleted
        return total
