"""Tests for Mercado Pago payment search helpers."""

from unittest.mock import patch

from django.test import SimpleTestCase

from api.mercadopago.search import search_payments_all_in_range


class SearchPaymentsAllInRangeTests(SimpleTestCase):
    def test_http_error_includes_api_message(self):
        raw = {
            "status": 400,
            "response": {"message": "Invalid filters", "error": "bad_request"},
        }
        with patch(
            "api.mercadopago.search.search_payments",
            return_value=raw,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                search_payments_all_in_range(
                    begin_date="2026-01-01T00:00:00.000Z",
                    end_date="2026-03-24T23:59:59.000Z",
                )
        self.assertIn("400", str(ctx.exception))
        self.assertIn("Invalid filters", str(ctx.exception))
