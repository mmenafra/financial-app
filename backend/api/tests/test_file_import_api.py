"""Tests for FileImport list pagination and re-run."""

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from api.models import FileImport, ImportStatus, Source

User = get_user_model()

_BSA_MIN = (
    b";Cartola\n"
    b";Numero Cuenta : 97-10525-46\n"
    b";Fecha Desde : 01/04/2026\n"
    b";Fecha Hasta : 20/04/2026\n"
    b"Fecha;Descripcion;NroDoc.;Cargos;Abonos;Saldo\n"
    b"01042026;TRANSF. A CTA.CTE. POR SWEB;00000000;0000000854000,00;;+0000005574672,00\n"
    b"02042026;TEF 76984166-0 PROPIEDADES SAR;00000000;;0000000747040,00;+0000006139989,00\n"
)


class FileImportListAndRerunTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fi-user",
            email="fi@example.com",
            password="StrongPass123!",
        )
        self.client.force_authenticate(user=self.user)

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("file-import-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_pagination_returns_envelope(self):
        for i in range(6):
            FileImport.objects.create(
                user=self.user,
                source=Source.BANK_ACCOUNT,
                file=SimpleUploadedFile(
                    f"s{i}.dat",
                    _BSA_MIN,
                    content_type="application/octet-stream",
                ),
                original_filename=f"s{i}.dat",
                status=ImportStatus.COMPLETED,
                rows_imported=0,
                rows_skipped=0,
            )

        response = self.client.get(
            reverse("file-import-list"),
            {"page": 1, "page_size": 5},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 6)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(len(response.data["results"]), 5)

    def test_rerun_bank_creates_new_file_import(self):
        imp_url = reverse("import-bank-statement")
        statement = SimpleUploadedFile(
            "BSA.dat",
            _BSA_MIN,
            content_type="text/plain",
        )
        r1 = self.client.post(imp_url, {"file": statement}, format="multipart")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FileImport.objects.filter(user=self.user).count(), 1)
        first_fi = FileImport.objects.get(user=self.user)

        rerun_url = reverse("file-import-re-run", kwargs={"pk": str(first_fi.pk)})
        r2 = self.client.post(rerun_url, {}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(FileImport.objects.filter(user=self.user).count(), 2)
        self.assertIn("file_import", r2.data)
        self.assertIn("import_result", r2.data)
        new_id = r2.data["file_import"]["id"]
        self.assertNotEqual(new_id, str(first_fi.pk))
        new_fi = FileImport.objects.get(pk=new_id)
        self.assertEqual(new_fi.status, ImportStatus.COMPLETED)
        first_fi.refresh_from_db()
        self.assertEqual(first_fi.status, ImportStatus.COMPLETED)
