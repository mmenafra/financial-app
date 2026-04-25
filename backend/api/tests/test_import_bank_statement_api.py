from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

User = get_user_model()


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

    def test_import_parses_bsa_file(self):
        self.client.force_authenticate(user=self.user)
        content = (
            b";Cartola\n"
            b";Numero Cuenta : 97-10525-46\n"
            b";Fecha Desde : 01/04/2026\n"
            b";Fecha Hasta : 20/04/2026\n"
            b"Fecha;Descripcion;NroDoc.;Cargos;Abonos;Saldo\n"
            b"01042026;TRANSF. A CTA.CTE. POR SWEB;00000000;0000000854000,00;;+0000005574672,00\n"
            b"02042026;TEF 76984166-0 PROPIEDADES SAR;00000000;;0000000747040,00;+0000006139989,00\n"
        )
        statement = SimpleUploadedFile("BSA.dat", content, content_type="text/plain")

        response = self.client.post(self.url, {"file": statement}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["metadata"]["Numero Cuenta"], "97-10525-46")
        self.assertEqual(len(response.data["transactions"]), 2)
        self.assertEqual(response.data["transactions"][0]["date"], "2026-04-01")
        self.assertEqual(
            response.data["transactions"][0]["debit"], Decimal("854000.00")
        )
        self.assertIsNone(response.data["transactions"][0]["credit"])
        self.assertEqual(
            response.data["transactions"][1]["credit"], Decimal("747040.00")
        )
        self.assertEqual(
            response.data["transactions"][1]["balance"], Decimal("6139989.00")
        )

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
