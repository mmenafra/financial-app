"""Shared statement import processing used by API views and file-import re-run."""

import logging
from datetime import date

from rest_framework import status
from rest_framework.response import Response

from .bank_statement_parser import parse_bsa_bank_statement
from .bsa_import import import_bsa_row
from .gemini_categorize import run_bulk_categorization
from .models import (
    FileImport,
    ImportStatus,
    Source,
    Transaction,
    UserProfile,
    VisaInternationalStatement,
)
from .serializers import TransactionSerializer
from .visa_internacional_import import (
    import_visa_internacional_row,
    sum_visa_internacional_parsed_expenses_usd,
)
from .visa_internacional_parser import parse_visa_internacional_statement_pdf
from .visa_nacional_parser import parse_visa_nacional_statement_pdf

logger = logging.getLogger(__name__)


def _refresh_transactions_preserving_order(
    instances: list[Transaction],
) -> list[Transaction]:
    if not instances:
        return instances
    pks_ordered = [t.pk for t in instances]
    fresh = Transaction.objects.filter(pk__in=pks_ordered)
    by_pk = {t.pk: t for t in fresh}
    return [by_pk[pk] for pk in pks_ordered if pk in by_pk]


def gemini_bulk_metadata_after_bank_import(
    user, created_instances: list[Transaction]
) -> tuple[bool, bool, str | None]:
    attempted = False
    failed = False
    failure_detail: str | None = None
    pending_uncat = [inst for inst in created_instances if inst.category_id is None]
    if not pending_uncat:
        return attempted, failed, failure_detail

    profile = UserProfile.objects.filter(user=user).first()
    api_key = profile.get_gemini_api_key() if profile else None
    if not api_key:
        return attempted, failed, failure_detail

    ai_state = run_bulk_categorization(user, pending_uncat, api_key)
    attempted = ai_state["attempted"]
    failed = bool(ai_state["attempted"] and not ai_state["applied"])
    failure_detail = ai_state["failure_detail"]
    return attempted, failed, failure_detail


def bank_statement_import_pipeline(request, file_import):
    """
    Parse BSA file content from stored FileImport and persist rows.
    Mutates `file_import`. Returns 201 Response or 400 Response.
    """
    try:
        file_import.file.open("rb")
        try:
            content = file_import.file.read().decode("utf-8")
        finally:
            file_import.file.close()
        logger.debug(
            "Bank statement file decoded, length=%s characters", len(content)
        )
        parsed = parse_bsa_bank_statement(content)
    except UnicodeDecodeError as exc:
        logger.error("Bank statement UTF-8 decode failed: %s", exc)
        file_import.status = ImportStatus.FAILED
        file_import.error_message = "File must be UTF-8 encoded text."
        file_import.save(update_fields=["status", "error_message", "updated_at"])
        return Response(
            {"detail": "File must be UTF-8 encoded text."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ValueError as exc:
        logger.error("Bank statement parse failed: %s", exc)
        file_import.status = ImportStatus.FAILED
        file_import.error_message = str(exc)
        file_import.save(update_fields=["status", "error_message", "updated_at"])
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created_count = 0
    skipped_count = 0
    failed_count = 0
    created_instances = []
    errors: list[dict] = []
    for row in parsed.get("transactions", []):
        result = import_bsa_row(request.user, row, file_import=file_import)
        if "error" in result:
            failed_count += 1
            errors.append({"row": row, "error": result["error"]})
            continue
        if result.get("ok") == "skipped":
            skipped_count += 1
        elif result.get("ok") == "created" and result.get("instance"):
            created_count += 1
            created_instances.append(result["instance"])

    logger.info(
        "Import bank statement persist: user_id=%s created=%s skipped=%s failed=%s",
        request.user.pk,
        created_count,
        skipped_count,
        failed_count,
    )

    ai_categorization_attempted, ai_categorization_failed, ai_failure_detail = (
        gemini_bulk_metadata_after_bank_import(request.user, created_instances)
    )
    created_instances = _refresh_transactions_preserving_order(created_instances)

    file_import.rows_imported = created_count
    file_import.rows_skipped = skipped_count
    file_import.status = ImportStatus.COMPLETED
    file_import.save(
        update_fields=[
            "rows_imported",
            "rows_skipped",
            "status",
            "updated_at",
        ]
    )
    ser = TransactionSerializer(
        created_instances, many=True, context={"request": request}
    )
    response_body = {
        "created": created_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "transactions": ser.data,
        "errors": errors,
        "ai_categorization_attempted": ai_categorization_attempted,
        "ai_categorization_failed": ai_categorization_failed,
        "ai_failure_detail": ai_failure_detail,
    }
    return Response(response_body, status=status.HTTP_201_CREATED)


def visa_nacional_import_pipeline(_request, file_import):
    """Parse Visa Nacional PDF from stored FileImport. Mutates `file_import`."""
    try:
        file_import.file.open("rb")
        try:
            pdf_bytes = file_import.file.read()
        finally:
            file_import.file.close()
        logger.debug("Visa Nacional PDF size=%s bytes", len(pdf_bytes))
        parsed = parse_visa_nacional_statement_pdf(pdf_bytes)
    except ValueError as exc:
        logger.error("Visa Nacional import failed: %s", exc)
        file_import.status = ImportStatus.FAILED
        file_import.error_message = str(exc)
        file_import.save(update_fields=["status", "error_message", "updated_at"])
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tx_count = len(parsed.get("transactions", []))
    logger.info(
        "Import Visa Nacional success: transactions=%s",
        tx_count,
    )
    file_import.rows_imported = tx_count
    file_import.rows_skipped = 0
    file_import.status = ImportStatus.COMPLETED
    file_import.save(
        update_fields=[
            "rows_imported",
            "rows_skipped",
            "status",
            "updated_at",
        ]
    )
    return Response(parsed, status=status.HTTP_200_OK)


def visa_internacional_import_pipeline(request, file_import):
    """Parse Visa Internacional PDF from stored FileImport and persist rows. Mutates `file_import`."""
    try:
        file_import.file.open("rb")
        try:
            pdf_bytes = file_import.file.read()
        finally:
            file_import.file.close()
        logger.debug("Visa Internacional PDF size=%s bytes", len(pdf_bytes))
        parsed = parse_visa_internacional_statement_pdf(pdf_bytes)
    except ValueError as exc:
        logger.error("Visa Internacional import failed: %s", exc)
        file_import.status = ImportStatus.FAILED
        file_import.error_message = str(exc)
        file_import.save(update_fields=["status", "error_message", "updated_at"])
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    rows = parsed.get("transactions", [])
    period_start = date.fromisoformat(parsed["period_from"])
    period_end = date.fromisoformat(parsed["period_to"])
    total_amount = sum_visa_internacional_parsed_expenses_usd(rows)
    visa_statement = VisaInternationalStatement.objects.create(
        user=request.user,
        file_import=file_import,
        period_start=period_start,
        period_end=period_end,
        total_amount=total_amount,
        currency="USD",
    )

    created_count = 0
    skipped_count = 0
    failed_count = 0
    created_instances = []
    errors: list[dict] = []
    for row in rows:
        result = import_visa_internacional_row(
            request.user,
            row,
            file_import=file_import,
            visa_statement=visa_statement,
        )
        if "error" in result:
            failed_count += 1
            errors.append({"row": row, "error": result["error"]})
            continue
        if result.get("ok") == "skipped":
            skipped_count += 1
        elif result.get("ok") == "created" and result.get("instance"):
            created_count += 1
            created_instances.append(result["instance"])

    logger.info(
        "Import Visa Internacional persist: user_id=%s created=%s skipped=%s failed=%s",
        request.user.pk,
        created_count,
        skipped_count,
        failed_count,
    )

    ai_categorization_attempted, ai_categorization_failed, ai_failure_detail = (
        gemini_bulk_metadata_after_bank_import(request.user, created_instances)
    )
    created_instances = _refresh_transactions_preserving_order(created_instances)

    file_import.rows_imported = created_count
    file_import.rows_skipped = skipped_count
    file_import.status = ImportStatus.COMPLETED
    file_import.save(
        update_fields=[
            "rows_imported",
            "rows_skipped",
            "status",
            "updated_at",
        ]
    )
    ser = TransactionSerializer(
        created_instances, many=True, context={"request": request}
    )
    response_body = {
        "created": created_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "transactions": ser.data,
        "errors": errors,
        "ai_categorization_attempted": ai_categorization_attempted,
        "ai_categorization_failed": ai_categorization_failed,
        "ai_failure_detail": ai_failure_detail,
    }
    return Response(response_body, status=status.HTTP_201_CREATED)


def dispatch_import_pipeline(request, file_import):
    """Run pipeline for `file_import.source`. Returns Response."""
    file_import.status = ImportStatus.PROCESSING
    file_import.save(update_fields=["status", "updated_at"])

    if file_import.source == Source.BANK_ACCOUNT:
        return bank_statement_import_pipeline(request, file_import)
    if file_import.source == Source.CREDIT_CARD_NATIONAL:
        return visa_nacional_import_pipeline(request, file_import)
    if file_import.source == Source.CREDIT_CARD_INTERNATIONAL:
        return visa_internacional_import_pipeline(request, file_import)

    file_import.status = ImportStatus.FAILED
    file_import.error_message = (
        f"Imports cannot be re-run for source {file_import.source}."
    )
    file_import.save(update_fields=["status", "error_message", "updated_at"])
    return Response(
        {"detail": file_import.error_message},
        status=status.HTTP_400_BAD_REQUEST,
    )


def copy_file_import_upload(existing: FileImport):
    """
    Read stored file from `existing` and return kwargs suitable for a new FileImport
    ({file: ContentFile, original_filename: str}) or raise OSError.
    """
    from django.core.files.base import ContentFile

    existing.file.open("rb")
    try:
        data = existing.file.read()
    finally:
        existing.file.close()
    content_file = ContentFile(data, name=existing.original_filename)
    return content_file
