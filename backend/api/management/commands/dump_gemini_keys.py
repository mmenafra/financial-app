"""Dump decrypted Gemini API keys for all users with a stored key (operator-only)."""

from cryptography.fernet import InvalidToken

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.models import UserProfile


class Command(BaseCommand):
    help = (
        "Print username and decrypted Gemini API key for each user profile that has one. "
        "Refuses when DEBUG=False unless --insecure is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--insecure",
            action="store_true",
            help="Required when DEBUG is False; acknowledges plaintext secrets on stdout.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["insecure"]:
            raise CommandError(
                "Refusing to dump Gemini keys while DEBUG=False. "
                "For recovery on a trusted host, run again with --insecure."
            )

        self.stderr.write(
            self.style.WARNING(
                "WARNING: plaintext API keys follow — redirect or clear shell history as needed."
            )
        )

        rows = (
            UserProfile.objects.select_related("user")
            .exclude(_gemini_api_key=None)
            .order_by("user__username")
        )
        count = 0
        for profile in rows:
            username = profile.user.username
            try:
                key = profile.get_gemini_api_key()
            except InvalidToken as exc:
                self.stderr.write(
                    self.style.ERROR(f"{username}\t<decrypt failed: {exc}>")
                )
                continue
            if not key:
                continue
            count += 1
            self.stdout.write(f"{username}\t{key}")

        if count == 0:
            self.stdout.write("(no users with a stored Gemini key)")
