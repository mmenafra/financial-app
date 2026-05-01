"""Tests for dump_gemini_keys management command."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from api.models import UserProfile

User = get_user_model()


class DumpGeminiKeysTests(TestCase):
    def test_debug_false_requires_insecure(self):
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                call_command("dump_gemini_keys")

    @override_settings(DEBUG=False)
    def test_insecure_allowed_when_debug_false(self):
        out = StringIO()
        err = StringIO()
        call_command(
            "dump_gemini_keys", "--insecure", stdout=out, stderr=err, verbosity=0
        )
        self.assertIn("no users", out.getvalue().lower())

    @override_settings(DEBUG=True)
    def test_prints_username_and_key_when_debug_true(self):
        user = User.objects.create_user(
            username="key-holder",
            email="kh@example.com",
            password="StrongPass123!",
        )
        profile, _created = UserProfile.objects.get_or_create(user=user)
        profile.set_gemini_api_key("secret-api-key-value")
        profile.save(update_fields=["_gemini_api_key", "updated_at"])

        out = StringIO()
        err = StringIO()
        call_command("dump_gemini_keys", stdout=out, stderr=err, verbosity=0)
        captured = out.getvalue()
        self.assertIn("key-holder", captured)
        self.assertIn("secret-api-key-value", captured)
