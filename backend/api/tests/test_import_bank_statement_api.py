import json
from decimal import Decimal
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from api.models import (
    Category,
    Direction,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
    UserProfile,
)

User = get_user_model()

_BSA_BASE = (
    b";Cartola\n"
    b";Numero Cuenta : 97-10525-46\n"
    b";Fecha Desde : 01/04/2026\n"
    b";Fecha Hasta : 20/04/2026\n"
    b"Fecha;Descripcion;NroDoc.;Cargos;Abonos;Saldo\n"
    b"01042026;TRANSF. A CTA.CTE. POR SWEB;00000000;0000000854000,00;;+0000005574672,00\n"
    b"02042026;TEF 76984166-0 PROPIEDADES SAR;00000000;;0000000747040,00;+0000006139989,00\n"
)


class ImportBankStatementAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="statement-user",
            email="statement@example.com",
            password="StrongPass123!",
        )
        self.url = reverse("import-bank-statement")

    def test_endpoint_requires_authentication(self):
        statement = SimpleUploadedFile(
            "statement.dat",
            b";Cartola\nFecha;Descripcion;NroDoc.;Cargos;Abonos;Saldo\n",
            content_type="text/plain",
        )
        response = self.client.post(self.url, {"file": statement}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_import_creates_transactions(self):
        self.client.force_authenticate(user=self.user)
        statement = SimpleUploadedFile("BSA.dat", _BSA_BASE, content_type="text/plain")

        response = self.client.post(self.url, {"file": statement}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["skipped"], 0)
        self.assertEqual(response.data["failed"], 0)
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["transactions"]), 2)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)

        txs = {t["description"]: t for t in response.data["transactions"]}
        t1 = txs["TRANSF. A CTA.CTE. POR SWEB"]
        t2 = txs["TEF 76984166-0 PROPIEDADES SAR"]
        self.assertEqual(t1["direction"], "EXPENSE")
        self.assertEqual(Decimal(t1["amount"]), Decimal("854000.00"))
        self.assertEqual(t1["source"], Source.BANK_ACCOUNT)
        self.assertEqual(t1["original_reference"], "00000000")
        self.assertIn("2026-04-01", t1["created_at"])
        self.assertEqual(t2["direction"], "INCOME")
        self.assertEqual(Decimal(t2["amount"]), Decimal("747040.00"))
        self.assertIn("2026-04-02", t2["created_at"])
        self.assertFalse(response.data["ai_categorization_attempted"])
        self.assertFalse(response.data["ai_categorization_failed"])

    def test_import_deduplication(self):
        self.client.force_authenticate(user=self.user)
        r1 = self.client.post(
            self.url,
            {"file": SimpleUploadedFile("BSA.dat", _BSA_BASE, content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.data["created"], 2)
        r2 = self.client.post(
            self.url,
            {"file": SimpleUploadedFile("BSA.dat", _BSA_BASE, content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.data["created"], 0)
        self.assertEqual(r2.data["skipped"], 2)
        self.assertEqual(r2.data["failed"], 0)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)

    def test_import_category_inference(self):
        self.client.force_authenticate(user=self.user)
        cat = Category.objects.create(
            name="Renta", user=self.user, icon="home", color="#f59e0b"
        )
        desc = "TEF 76984166-0 PROPIEDADES SAR"
        Transaction.objects.create(
            user=self.user,
            description=desc,
            amount=Decimal("1.00"),
            currency="CLP",
            transaction_type=TransactionType.CREDIT,
            direction=Direction.INCOME,
            source=Source.BANK_ACCOUNT,
            category=cat,
            external_id="manual-prior-1",
            status=TransactionStatus.CONFIRMED,
        )
        statement = SimpleUploadedFile("BSA.dat", _BSA_BASE, content_type="text/plain")
        response = self.client.post(self.url, {"file": statement}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        for row in response.data["transactions"]:
            if row["description"] == desc:
                self.assertEqual(str(row["category"]), str(cat.id))
                return
        self.fail("expected imported row with TEF description")

    def test_import_category_inference_normalizes_whitespace(self):
        self.client.force_authenticate(user=self.user)
        cat = Category.objects.create(
            name="TestCat", user=self.user, icon="home", color="#f59e0b"
        )
        Transaction.objects.create(
            user=self.user,
            description="MERCHANT  NAME    HERE",
            amount=Decimal("1.00"),
            currency="CLP",
            transaction_type=TransactionType.DEBIT,
            direction=Direction.EXPENSE,
            source=Source.BANK_ACCOUNT,
            category=cat,
            external_id="manual-prior-ws",
            status=TransactionStatus.CONFIRMED,
        )
        one_row = (
            b";Cartola\n"
            b";Numero Cuenta : 97-10525-46\n"
            b";Fecha Desde : 01/04/2026\n"
            b";Fecha Hasta : 20/04/2026\n"
            b"Fecha;Descripcion;NroDoc.;Cargos;Abonos;Saldo\n"
            b"01042026;MERCHANT NAME HERE;00000001;0000000010000,00;;+0000005574672,00\n"
        )
        statement = SimpleUploadedFile("BSA.dat", one_row, content_type="text/plain")
        response = self.client.post(self.url, {"file": statement}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["transactions"]), 1)
        tx = response.data["transactions"][0]
        self.assertEqual(tx["description"], "MERCHANT  NAME    HERE")
        self.assertEqual(str(tx["category"]), str(cat.id))

    def test_import_errors_included_in_response(self):
        self.client.force_authenticate(user=self.user)
        content = (
            _BSA_BASE
            + b"01042026;NO_AMOUNT;00000000;;;+0000000001,00\n"  # no debit, no credit
        )
        statement = SimpleUploadedFile("BSA.dat", content, content_type="text/plain")
        response = self.client.post(self.url, {"file": statement}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["failed"], 1)
        self.assertEqual(len(response.data["errors"]), 1)
        err = response.data["errors"][0]
        self.assertIn("row", err)
        self.assertIn("error", err)
        self.assertIn("neither", err["error"].lower())
        # Two good rows from base + one bad
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)

    def test_only_dat_files_are_supported(self):
        self.client.force_authenticate(user=self.user)
        statement = SimpleUploadedFile(
            "statement.txt",
            b"Fecha;Descripcion;NroDoc.;Cargos;Abonos;Saldo\n",
            content_type="text/plain",
        )
        response = self.client.post(self.url, {"file": statement}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Only .dat files are supported.")


def _parsed_context_from_gemini_body(body: dict):
    txt = body["contents"][0]["parts"][0]["text"]
    start = txt.index("{")
    return json.loads(txt[start:])


@override_settings(GEMINI_HTTP_ENABLED=True)
class GeminiBankStatementImportTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="gemini-import-user",
            email="gemini-import@example.com",
            password="StrongPass123!",
        )
        self.url = reverse("import-bank-statement")
        self.cat = Category.objects.create(
            name="AutoCat", user=self.user, icon="tag", color="#c026d3"
        )
        self.profile, _created = UserProfile.objects.get_or_create(user=self.user)
        self.profile.set_gemini_api_key("fake-gemini-test-key-placeholder")
        self.profile.save(update_fields=["_gemini_api_key", "updated_at"])

    def test_gemini_applies_bulk_categories_via_mock(self):
        def stub(_, body, **_kwargs):  # noqa: ANN001
            blob = _parsed_context_from_gemini_body(body)
            cid = blob["categories"][0]["id"]
            return {
                "assignments": [
                    {"transaction_id": t["id"], "category_id": cid}
                    for t in blob["transactions"]
                ],
            }

        self.client.force_authenticate(user=self.user)
        statement = SimpleUploadedFile("BSA.dat", _BSA_BASE, content_type="text/plain")
        with patch("api.gemini_categorize._call_gemini_raw", side_effect=stub):
            response = self.client.post(self.url, {"file": statement}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 2)
        self.assertTrue(response.data["ai_categorization_attempted"])
        self.assertFalse(response.data["ai_categorization_failed"])
        for tx in response.data["transactions"]:
            self.assertEqual(str(tx["category"]), str(self.cat.id))

    def test_gemini_soft_failure_leaves_uncategorized_rows(self):
        def boom(_, body, **_kwargs):  # noqa: ANN001
            _ = body
            raise RuntimeError("simulated Gemini outage")

        self.client.force_authenticate(user=self.user)
        statement = SimpleUploadedFile("BSA.dat", _BSA_BASE, content_type="text/plain")
        with patch("api.gemini_categorize._call_gemini_raw", side_effect=boom):
            response = self.client.post(self.url, {"file": statement}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["ai_categorization_attempted"])
        self.assertTrue(response.data["ai_categorization_failed"])
        self.assertIn("Gemini outage", response.data["ai_failure_detail"])
        for tx in response.data["transactions"]:
            self.assertIsNone(tx["category"])
