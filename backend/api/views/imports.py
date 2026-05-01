import logging

from drf_spectacular.utils import (
    OpenApiRequest,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..imports.pipeline import (
    bank_statement_import_pipeline,
    visa_internacional_import_pipeline,
    visa_nacional_import_pipeline,
)
from ..models import FileImport, ImportStatus, Source
from ..serializers import (
    ImportBankStatementSerializer,
    ImportVisaInternationalStatementSerializer,
    ImportVisaNationalStatementSerializer,
    TransactionSerializer,
)

logger = logging.getLogger(__name__)


class ImportBankStatementView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=OpenApiRequest(
            request=ImportBankStatementSerializer,
            encoding={"file": {"contentType": "application/octet-stream"}},
        ),
        responses={
            201: inline_serializer(
                name="ImportBankStatementPersistResponse",
                fields={
                    "created": serializers.IntegerField(),
                    "skipped": serializers.IntegerField(),
                    "failed": serializers.IntegerField(),
                    "transactions": TransactionSerializer(many=True),
                    "errors": serializers.ListField(
                        child=inline_serializer(
                            name="ImportBankStatementRowError",
                            fields={
                                "row": serializers.JSONField(),
                                "error": serializers.CharField(),
                            },
                        )
                    ),
                    "ai_categorization_attempted": serializers.BooleanField(),
                    "ai_categorization_failed": serializers.BooleanField(),
                    "ai_failure_detail": serializers.CharField(
                        required=False,
                        allow_null=True,
                        allow_blank=True,
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid file payload"),
        },
    )
    def post(self, request):
        statement_file = request.FILES.get("file")
        if not statement_file:
            return Response(
                {"detail": "A file is required in form-data with key 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not statement_file.name.lower().endswith(".dat"):
            return Response(
                {"detail": "Only .dat files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import bank statement: user_id=%s filename=%r",
            request.user.pk,
            statement_file.name,
        )
        file_import = FileImport.objects.create(
            user=request.user,
            source=Source.BANK_ACCOUNT,
            file=statement_file,
            original_filename=statement_file.name,
            status=ImportStatus.PENDING,
        )
        file_import.status = ImportStatus.PROCESSING
        file_import.save(update_fields=["status", "updated_at"])

        return bank_statement_import_pipeline(request, file_import)


class ImportVisaNationalStatementView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=OpenApiRequest(
            request=ImportVisaNationalStatementSerializer,
            encoding={"file": {"contentType": "application/pdf"}},
        ),
        responses={
            200: inline_serializer(
                name="ImportVisaNationalResponse",
                fields={
                    "transactions": serializers.ListField(
                        child=serializers.JSONField()
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid file payload or PDF"),
        },
    )
    def post(self, request):
        statement_file = request.FILES.get("file")
        if not statement_file:
            return Response(
                {"detail": "A file is required in form-data with key 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not statement_file.name.lower().endswith(".pdf"):
            return Response(
                {"detail": "Only .pdf files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import Visa Nacional: user_id=%s filename=%r",
            request.user.pk,
            statement_file.name,
        )
        file_import = FileImport.objects.create(
            user=request.user,
            source=Source.CREDIT_CARD_NATIONAL,
            file=statement_file,
            original_filename=statement_file.name,
            status=ImportStatus.PENDING,
        )
        file_import.status = ImportStatus.PROCESSING
        file_import.save(update_fields=["status", "updated_at"])

        return visa_nacional_import_pipeline(request, file_import)


class ImportVisaInternationalStatementView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request=OpenApiRequest(
            request=ImportVisaInternationalStatementSerializer,
            encoding={"file": {"contentType": "application/pdf"}},
        ),
        responses={
            200: inline_serializer(
                name="ImportVisaInternationalResponse",
                fields={
                    "transactions": serializers.ListField(
                        child=serializers.JSONField()
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid file payload or PDF"),
        },
    )
    def post(self, request):
        statement_file = request.FILES.get("file")
        if not statement_file:
            return Response(
                {"detail": "A file is required in form-data with key 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not statement_file.name.lower().endswith(".pdf"):
            return Response(
                {"detail": "Only .pdf files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Import Visa Internacional: user_id=%s filename=%r",
            request.user.pk,
            statement_file.name,
        )
        file_import = FileImport.objects.create(
            user=request.user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            file=statement_file,
            original_filename=statement_file.name,
            status=ImportStatus.PENDING,
        )
        file_import.status = ImportStatus.PROCESSING
        file_import.save(update_fields=["status", "updated_at"])

        return visa_internacional_import_pipeline(request, file_import)
