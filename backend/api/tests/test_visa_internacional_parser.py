from datetime import date

from django.test import SimpleTestCase

from api.visa_internacional_parser import (
    parse_transaction_line_body,
    parse_visa_internacional_statement_text,
    resolve_dd_mm_in_period,
)


class VisaInternacionalParserTests(SimpleTestCase):
    FIXTURE_MAR_2026 = """
II. DETALLE
Período Facturado Desde
Período Facturado Hasta
CUPO TOTAL CUPO UTILIZADO CUPO DISPONIBLE
24/02/2026
23/03/2026
US$ 122,84
2. INFORMACIÓN DE TRANSACCIONES
Número Referencia
Fecha
Operación
00/00 TOTAL PAGOS 00 0,00 0,00
000000001508127908 06/03 PAGO EN EFECTIVO -122,84 -122,84
00/00 TOTAL COMPRAS 00 0,00 0,00
000000001498572431 25/02 NETFLIX.COM 844-5052993 CA 21,46 16,15
000000001502004568 01/03 Patreon* Membership Internet IE 32,73 32,73
-- 1 of 2 --
2. INFORMACIÓN DE TRANSACCIONES
000000001502054787 01/03 Google Workspace_callelat 650-2530000 US 8,40 8,40
000000001513211952 12/03 Dropbox QT4PW1C9233T db.tt/cchelp IE 11,99 11,99
00/00 COMISIONES, OTROS CARGOS Y ABONOS A LA 00 0,00 0,00
-- 2 of 2 --
"""

    FIXTURE_FEB_2026_UBER = """
II. DETALLE
24/01/2026
23/02/2026
2. INFORMACIÓN DE TRANSACCIONES
00/00 TOTAL PAGOS 00 0,00 0,00
000000001470144658 30/01 UBER *TRIP
HELP.UBER.COM
NL 955,12 25,55
00/00 COMISIONES 00 0,00 0,00
"""

    FIXTURE_DEC_JAN = """
II. DETALLE
24/12/2025
23/01/2026
2. INFORMACIÓN DE TRANSACCIONES
000000001432528071 25/12 Netflix.com 866-716-0414 CA 21,46 16,18
000000001438630256 01/01 Patreon* Membership Internet IE 32,73 32,73
"""

    def test_parse_line_body_pago(self):
        out = parse_transaction_line_body("PAGO EN EFECTIVO -122,84 -122,84")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIsNone(out["country"])
        self.assertEqual(out["description"], "PAGO EN EFECTIVO")
        self.assertEqual(out["amount_local"], "-122.84")
        self.assertEqual(out["amount_usd"], "-122.84")

    def test_parse_line_body_uyu_thousands(self):
        out = parse_transaction_line_body("DISCO N? 5 PUNTA DEL EST UY 1.020,45 28,02")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["country"], "UY")
        self.assertIn("PUNTA DEL EST", out["description"])
        self.assertEqual(out["amount_local"], "1020.45")
        self.assertEqual(out["amount_usd"], "28.02")

    def test_parse_line_body_us_country(self):
        out = parse_transaction_line_body("Google 650-2530000 US 8,40 8,40")
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["country"], "US")
        self.assertEqual(out["amount_usd"], "8.40")

    def test_resolve_date_across_new_year(self):
        d = resolve_dd_mm_in_period(
            "25/12",
            date(2025, 12, 24),
            date(2026, 1, 23),
        )
        self.assertEqual(d, "2025-12-25")
        d2 = resolve_dd_mm_in_period(
            "01/01",
            date(2025, 12, 24),
            date(2026, 1, 23),
        )
        self.assertEqual(d2, "2026-01-01")

    def test_resolve_date_prefers_closest_when_outside_billing_window(self):
        # No 15/01 falls inside an all-March period; we still return a date (closest).
        d = resolve_dd_mm_in_period(
            "15/01",
            date(2026, 3, 1),
            date(2026, 3, 31),
        )
        self.assertEqual(d, "2026-01-15")

    def test_parse_mar_2026_fixture_five_rows(self):
        out = parse_visa_internacional_statement_text(self.FIXTURE_MAR_2026)
        txs = out["transactions"]
        self.assertEqual(len(txs), 5)
        self.assertEqual(txs[0]["reference"], "000000001508127908")
        self.assertEqual(txs[0]["operation_date"], "2026-03-06")
        self.assertIsNone(txs[0]["country"])
        self.assertEqual(txs[1]["reference"], "000000001498572431")
        self.assertEqual(txs[1]["country"], "CA")
        self.assertEqual(txs[3]["description"], "Google Workspace_callelat 650-2530000")
        self.assertEqual(txs[3]["country"], "US")

    def test_parse_uber_multiline(self):
        out = parse_visa_internacional_statement_text(self.FIXTURE_FEB_2026_UBER)
        self.assertEqual(len(out["transactions"]), 1)
        t = out["transactions"][0]
        self.assertEqual(t["operation_date"], "2026-01-30")
        self.assertEqual(t["country"], "NL")
        self.assertIn("UBER *TRIP", t["description"])
        self.assertIn("HELP.UBER.COM", t["description"])
        self.assertEqual(t["amount_local"], "955.12")
        self.assertEqual(t["amount_usd"], "25.55")

    def test_parse_dec_jan_period(self):
        out = parse_visa_internacional_statement_text(self.FIXTURE_DEC_JAN)
        self.assertEqual(len(out["transactions"]), 2)
        self.assertEqual(out["transactions"][0]["operation_date"], "2025-12-25")
        self.assertEqual(out["transactions"][1]["operation_date"], "2026-01-01")
