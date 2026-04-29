"""Helpers for resolving which Visa Nacional statement row to use."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count

from .models import FileImport, VisaNacionalStatement


def reuse_or_create_nacional_statement_for_import(
    user,
    file_import: FileImport,
    period_end: date,
    total_amount: Decimal,
    currency: str = "CLP",
) -> VisaNacionalStatement:
    """
    One logical statement per (user, period_end) — closing date from the PDF.

    Re-imports update the chosen row's ``file_import`` / totals instead of inserting
    a duplicate. Prefers an existing row that already has transactions so skipped
    imports stay attached to the same statement the dashboard shows.
    """
    candidates = (
        VisaNacionalStatement.objects.filter(
            user=user,
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

    return VisaNacionalStatement.objects.create(
        user=user,
        file_import=file_import,
        period_end=period_end,
        total_amount=total_amount,
        currency=currency,
    )


def select_nacional_statement_for_period_end_month(
    user, year: int, month: int
) -> VisaNacionalStatement | None:
    """
    Pick the statement to show for a closing month when duplicates may exist.

    Prefer the row with the most linked transactions (the one that actually holds
    imported rows), then the newest by ``created_at`` for metadata such as totals.
    """
    return (
        VisaNacionalStatement.objects.filter(
            user=user,
            period_end__year=year,
            period_end__month=month,
        )
        .annotate(_tx_count=Count("transactions"))
        .order_by("-_tx_count", "-created_at")
        .first()
    )
