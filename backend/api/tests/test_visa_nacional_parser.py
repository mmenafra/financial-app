from decimal import Decimal

from django.test import SimpleTestCase

from api.visa_nacional_parser import (
    extract_periodo_actual_block,
    parse_transactions_from_periodo_text,
    parse_visa_nacional_statement_text,
)


class VisaNacionalParserTests(SimpleTestCase):
    """Parser tests use representative statement text (no PDF bytes)."""

    FIXTURE_TEXT = """II. DETALLE
1.PERÍODO ANTERIOR
23/01/2026 23/02/2026
$ 0
2.PERÍODO ACTUAL
Lugar de
Operación
1.TOTAL OPERACIONES $ 0
06/03/2026 0903
08128021
PAGO EN EFECTIVO $ -403.521 $ -403.521 01/01 $ -403.521
PAGOS A LA CUENTA $ 0
LAS
CONDES
26/02/2026 2602
98573229
MERPAGO*M 76516950K 76516950K $ 6.713 $ 6.713 01/01 $ 6.713
SANTIAGO 26/02/2026 2702
99818058
COMERCIALIZADORA STEVE DO $ 149.990 $ 149.990 01/01 $ 149.990
SANTIAGO 02/01/2026 1203
37250748
FALABELLA PZA. NORTE TASA INT. 0% $ 183.930 $ 183.930 03/03 $ 61.310
3.CARGOS, COMISIONES, IMPUESTOS Y ABONO $ 0
20/03/2026 2003
22117325
SERVICIO DE ACTIVIDAD MENSUAL $ 3.973 $ 3.973 01/01 $ 3.973
III. INFORMACIÓN DE PAGO
"""

    def test_extract_periodo_stops_before_section_3(self):
        block = extract_periodo_actual_block(self.FIXTURE_TEXT)
        self.assertIn("MERPAGO", block)
        self.assertNotIn("III.", block)
        self.assertNotIn("SERVICIO DE ACTIVIDAD MENSUAL", block)

    def test_parse_full_text_returns_transactions_only(self):
        out = parse_visa_nacional_statement_text(self.FIXTURE_TEXT)
        self.assertIn("transactions", out)
        self.assertEqual(len(out["transactions"]), 4)

    def test_negative_payment_amount(self):
        out = parse_visa_nacional_statement_text(self.FIXTURE_TEXT)
        pay = out["transactions"][0]
        self.assertEqual(pay["description"], "PAGO EN EFECTIVO")
        self.assertEqual(Decimal(pay["amount"]), Decimal("-403521"))

    def test_installment_fields(self):
        out = parse_visa_nacional_statement_text(self.FIXTURE_TEXT)
        falabella = next(
            t for t in out["transactions"] if "FALABELLA" in t["description"]
        )
        self.assertEqual(falabella["installment"], "03/03")
        self.assertEqual(Decimal(falabella["installment_value"]), Decimal("61310"))

    def test_parse_periodo_block_skips_section_3_lines(self):
        block = extract_periodo_actual_block(self.FIXTURE_TEXT)
        txs = parse_transactions_from_periodo_text(block)
        self.assertEqual(len(txs), 4)
