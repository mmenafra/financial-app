"""Helpers for resolving which Visa International statement row to use."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count

from ..models import FileImport, VisaInternationalStatement


def reuse_or_create_statement_for_import(
    user,
    file_import: FileImport,
    period_start: date,
    period_end: date,
    total_amount: Decimal,
    *,
    currency: str = "USD",
) -> VisaInternationalStatement:
    """
    One logical statement per (user, period_start, period_end).

    Re-imports update the chosen row's ``file_import`` / totals instead of inserting
    a duplicate. Prefers an existing row that already has transactions so skipped
    imports stay attached to the same statement the dashboard shows.
    """
    candidates = (
        VisaInternationalStatement.objects.filter(
            user=user,
            period_start=period_start,
            period_end=period_end,
        )
        .annotate(_tx_count=Count("transactions"))
        .order_by("-_tx_count", "created_at")
    )
    stmt = candidates.first()
    if stmt is not None:
        stmt.file_import = file_import
        stmt.total_amount = total_amount
        stmt.currency = currency
        stmt.save(
            update_fields=["file_import", "total_amount", "currency", "updated_at"]
        )
        return stmt

    return VisaInternationalStatement.objects.create(
        user=user,
        file_import=file_import,
        period_start=period_start,
        period_end=period_end,
        total_amount=total_amount,
        currency=currency,
    )


def select_statement_for_period_end_month(
    user, year: int, month: int
) -> VisaInternationalStatement | None:
    """
    Pick the statement to show for a closing month when duplicates may exist.

    Prefer the row with the most linked transactions (the one that actually holds
    imported rows), then the newest by ``created_at`` for metadata such as totals.
    """
    return (
        VisaInternationalStatement.objects.filter(
            user=user,
            period_end__year=year,
            period_end__month=month,
        )
        .annotate(_tx_count=Count("transactions"))
        .select_related("file_import")
        .order_by("-_tx_count", "-created_at")
        .first()
    )
