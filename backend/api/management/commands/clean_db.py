from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from api.models import Category, RecurringPattern, Transaction

User = get_user_model()


class Command(BaseCommand):
    help = "Clean DB data: all rows, all data for a user, or transactions only for a user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Delete ALL rows from Transaction, Category, RecurringPattern, and User tables.",
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

    def handle(self, *args, **options):
        if options["all"]:
            self._clean_all()
        elif options["user"]:
            self._clean_user(options["user"])
        elif options["transactions"]:
            self._clean_transactions(options["transactions"])
        else:
            raise CommandError(
                "Specify one of: --all, --user <username>, --transactions <username>"
            )

    def _clean_all(self):
        tx_count, _ = Transaction.objects.all().delete()
        cat_count, _ = Category.objects.all().delete()
        rp_count, _ = RecurringPattern.objects.all().delete()
        user_count, _ = User.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {tx_count} transactions, {cat_count} categories, "
                f"{rp_count} recurring patterns, {user_count} users."
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
