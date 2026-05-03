"""Unit tests for Visa Nacional Mercado Pago sync helpers."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from api.imports.mercadopago_nacional_sync import (
    add_calendar_months,
    mercadopago_search_window_iso_utc,
    mp_total_amount,
    sync_and_link_visa_nacional_statement,
    visa_description_is_mp_like,
)
from api.models import (
    Direction,
    FileImport,
    ImportStatus,
    MercadoPagoStoredPayment,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
    VisaNacionalStatement,
)

User = get_user_model()


class MercadoPagoNacionalSyncHelpersTests(TestCase):
    def test_add_calendar_months_clamps_day(self):
        self.assertEqual(add_calendar_months(date(2026, 3, 31), -2), date(2026, 1, 31))
        self.assertEqual(add_calendar_months(date(2026, 3, 15), -2), date(2026, 1, 15))

    def test_mercadopago_search_window_iso_utc_no_microseconds(self):
        begin, end = mercadopago_search_window_iso_utc(date(2026, 3, 24))
        self.assertEqual(begin, "2026-01-24T00:00:00.000Z")
        self.assertEqual(end, "2026-03-24T23:59:59.000Z")

    def test_mp_total_amount_prefers_transaction_details(self):
        pay = {
            "transaction_amount": 100,
            "transaction_details": {"total_paid_amount": 99.5},
        }
        self.assertEqual(mp_total_amount(pay), Decimal("99.5"))

    def test_mp_total_amount_falls_back_to_transaction_amount(self):
        pay = {"transaction_amount": 2500}
        self.assertEqual(mp_total_amount(pay), Decimal("2500"))

    def test_visa_description_is_mp_like(self):
        self.assertTrue(visa_description_is_mp_like("COMPRA MERCADOPAGO *FOO"))
        self.assertTrue(visa_description_is_mp_like("MERCADOLIBRE 123"))
        self.assertFalse(visa_description_is_mp_like("OTHER STORE"))


class MercadoPagoNacionalSyncLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="u1",
            email="u1@example.com",
            password="x",
        )
        self.file_import = FileImport.objects.create(
            user=self.user,
            source=Source.CREDIT_CARD_NATIONAL,
            file=ContentFile(b"x", name="vn.pdf"),
            original_filename="vn.pdf",
            status=ImportStatus.COMPLETED,
        )
        self.stmt = VisaNacionalStatement.objects.create(
            user=self.user,
            file_import=self.file_import,
            period_end=date(2026, 3, 24),
            total_amount=Decimal("1000"),
            currency="CLP",
        )
        self.tx = Transaction.objects.create(
            user=self.user,
            description="MERCADOPAGO *ITEM",
            amount=Decimal("15000"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.CREDIT_CARD_NATIONAL,
            status=TransactionStatus.CONFIRMED,
            visa_nacional_statement=self.stmt,
            transaction_date=date(2026, 3, 10),
        )

    @override_settings(MERCADOPAGO_ACCESS_TOKEN="tok")
    def test_sync_links_updates_description_from_mp_item_title(self):
        pay = {
            "id": 555001,
            "currency_id": "CLP",
            "transaction_amount": 15000,
            "transaction_details": {"total_paid_amount": 15000},
            "date_approved": "2026-03-10T12:00:00.000-04:00",
            "additional_info": {"items": [{"title": "Widget"}]},
        }
        with patch(
            "api.imports.mercadopago_nacional_sync.search_payments_all_in_range",
            return_value=[pay],
        ):
            out = sync_and_link_visa_nacional_statement(
                self.user, self.stmt, self.stmt.period_end
            )
        self.assertEqual(out["mercadopago_links_created"], 1)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.description, "Widget")
        self.assertEqual(self.tx.external_name, "Widget")
        sp = MercadoPagoStoredPayment.objects.get(mp_payment_id=555001)
        self.assertEqual(sp.visa_transaction_id, self.tx.pk)

    @override_settings(MERCADOPAGO_ACCESS_TOKEN="tok")
    def test_sync_links_keeps_visa_description_when_mp_has_no_display_title(self):
        pay = {
            "id": 555002,
            "currency_id": "CLP",
            "transaction_amount": 15000,
            "transaction_details": {"total_paid_amount": 15000},
            "date_approved": "2026-03-10T12:00:00.000-04:00",
        }
        desc_before = self.tx.description
        with patch(
            "api.imports.mercadopago_nacional_sync.search_payments_all_in_range",
            return_value=[pay],
        ):
            out = sync_and_link_visa_nacional_statement(
                self.user, self.stmt, self.stmt.period_end
            )
        self.assertEqual(out["mercadopago_links_created"], 1)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.description, desc_before)
        sp = MercadoPagoStoredPayment.objects.get(mp_payment_id=555002)
        self.assertEqual(sp.visa_transaction_id, self.tx.pk)

    @override_settings(MERCADOPAGO_ACCESS_TOKEN="tok")
    def test_sync_returns_error_message_on_mp_search_runtime_error(self):
        with patch(
            "api.imports.mercadopago_nacional_sync.search_payments_all_in_range",
            side_effect=RuntimeError(
                "Mercado Pago search HTTP 400: invalid range filter"
            ),
        ):
            out = sync_and_link_visa_nacional_statement(
                self.user, self.stmt, self.stmt.period_end
            )
        self.assertIn("mercadopago_sync_error", out)
        self.assertIn("400", out["mercadopago_sync_error"])
