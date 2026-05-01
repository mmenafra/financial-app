import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from django.db import IntegrityError, transaction
from django.db.models import Q

from ..imports.pipeline import copy_file_import_upload, dispatch_import_pipeline
from ..models import (
    FileImport,
    ImportStatus,
    RecurringPattern,
    Transaction,
    VisaInternationalStatement,
    VisaNacionalStatement,
)
from ..pagination import FileImportPagination
from ..serializers import FileImportSerializer, RecurringPatternSerializer

logger = logging.getLogger(__name__)


class FileImportViewSet(ModelViewSet):
    serializer_class = FileImportSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = FileImportPagination
    http_method_names = ["get", "head", "options", "post"]

    def get_queryset(self):
        return FileImport.objects.filter(user=self.request.user)

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(
                description=(
                    "New file_import row plus import_result "
                    "(same shape as the original import endpoint response)."
                ),
            ),
            400: OpenApiResponse(
                description="Invalid pipeline or unreadable stored file"
            ),
        },
        description=(
            "Re-process the stored file: creates a new FileImport row and runs "
            "the same pipeline as the original upload."
        ),
    )
    @action(detail=True, methods=["post"], url_path="re-run")
    def re_run(self, request, pk=None):  # pylint: disable=unused-argument
        existing = self.get_object()
        try:
            content_file = copy_file_import_upload(existing)
        except OSError:
            logger.warning(
                "Re-run import: could not read stored file for file_import id=%s",
                existing.pk,
            )
            return Response(
                {"detail": "Stored import file could not be read."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_fi = FileImport.objects.create(
            user=request.user,
            source=existing.source,
            file=content_file,
            original_filename=existing.original_filename,
            status=ImportStatus.PENDING,
        )
        pipeline_resp = dispatch_import_pipeline(request, new_fi)
        new_fi.refresh_from_db()
        ser = FileImportSerializer(new_fi, context={"request": request})
        payload: dict = {"file_import": ser.data}
        if pipeline_resp.status_code >= status.HTTP_400_BAD_REQUEST:
            detail = "Import failed."
            if isinstance(pipeline_resp.data, dict) and "detail" in pipeline_resp.data:
                detail = pipeline_resp.data["detail"]
            payload["detail"] = detail
            return Response(payload, status=pipeline_resp.status_code)
        payload["import_result"] = pipeline_resp.data
        return Response(payload, status=status.HTTP_200_OK)


class RecurringPatternViewSet(ModelViewSet):
    serializer_class = RecurringPatternSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RecurringPattern.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save(user=self.request.user)
        except IntegrityError as exc:
            raise ValidationError(
                detail="A recurring pattern with this match text and type already exists.",
            ) from exc

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise ValidationError(
                detail="A recurring pattern with this match text and type already exists.",
            ) from exc


class SubscriptionListView(APIView):
    """Recurring patterns that matched a txn on the user's latest Nacional/Intl Visa statements."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        latest_vn = (
            VisaNacionalStatement.objects.filter(user=user)
            .order_by("-period_end")
            .first()
        )
        latest_vi = (
            VisaInternationalStatement.objects.filter(user=user)
            .order_by("-period_end")
            .first()
        )
        if latest_vn is None and latest_vi is None:
            return Response([])

        stmt_filter = Q()
        if latest_vn:
            stmt_filter |= Q(visa_nacional_statement=latest_vn)
        if latest_vi:
            stmt_filter |= Q(visa_international_statement=latest_vi)

        qs = Transaction.objects.filter(
            user=user, matched_recurring_pattern__isnull=False
        ).filter(stmt_filter)

        txns = qs.select_related("matched_recurring_pattern").order_by(
            "-transaction_date", "-created_at"
        )

        seen: dict[str, Transaction] = {}
        for t in txns:
            pid = str(t.matched_recurring_pattern_id)
            if pid not in seen:
                seen[pid] = t

        result = []
        for t in seen.values():
            pat = t.matched_recurring_pattern
            result.append(
                {
                    "id": str(pat.id),
                    "name": pat.description_pattern,
                    "amount": str(t.amount),
                    "currency": t.currency,
                    "frequency": pat.frequency,
                    "last_matched_date": (
                        t.transaction_date.isoformat() if t.transaction_date else None
                    ),
                }
            )
        result.sort(key=lambda row: row["name"].lower())
        return Response(result)
