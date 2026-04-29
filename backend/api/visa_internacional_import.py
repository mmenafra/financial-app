"""Persist Visa Internacional (USD PDF) parsed rows as Transaction records."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

from .amounts import parse_chilean_decimal
from .bsa_import import bsa_row_json_safe, inferred_category_for_bsa
from .models import (
    Direction,
    FileImport,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
    VisaInternationalStatement,
)
from .recurring_match import match_recurring_pattern_for_description

logger = logging.getLogger(__name__)


def _persist_visa_created_dates_and_recurring_match(
    user, tx: Transaction, statement_dt: timezone.datetime
) -> None:
    """Back-date import timestamps and set ``matched_recurring_pattern`` when a rule matches."""
    Transaction.objects.filter(pk=tx.pk).update(
        created_at=statement_dt,
        imported_at=statement_dt,
    )
    tx.refresh_from_db()
    matched = match_recurring_pattern_for_description(user, tx.description)
    if matched is not None:
        Transaction.objects.filter(pk=tx.pk).update(matched_recurring_pattern=matched)
        tx.refresh_from_db()


def _visa_statement_dt(operation_date_iso: str) -> timezone.datetime:
    d = date.fromisoformat(operation_date_iso)
    dt = datetime.combine(d, time.min)
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def _decimal_from_row_field(val: Any, field_label: str) -> Decimal | None:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        # Chilean-style (thousands=. decimal=,) vs plain decimal-dot amounts.
        if "," in s:
            return parse_chilean_decimal(s)
        return Decimal(s)
    except (ValueError, InvalidOperation):
        logger.warning("Could not parse %s as decimal: %r", field_label, val)
        return None


def sum_visa_internacional_parsed_expenses_usd(rows: list[dict]) -> Decimal:
    """Sum of USD amounts for expense rows (positive ``amount_usd``), matching import direction rules."""
    total = Decimal("0")
    for row in rows:
        amount_usd = _decimal_from_row_field(row.get("amount_usd"), "amount_usd")
        if amount_usd is not None and amount_usd > 0:
            total += amount_usd
    return total


def import_visa_internacional_row(  # pylint: disable=too-many-return-statements  # noqa: C901
    user,
    row: dict,
    file_import: FileImport | None = None,
    visa_statement: VisaInternationalStatement | None = None,
) -> dict:
    """
    Import one Visa Internacional parsed row.

    Returns:
        {"ok": "created", "instance": Transaction}
        {"ok": "skipped", "instance": None}
        {"error": "..."}
    """
    try:
        ref_raw = row.get("reference")
        ref = str(ref_raw).strip() if ref_raw is not None else ""
        if not ref:
            return {"error": "Row is missing reference."}
        if len(ref) > 255:
            return {"error": "Reference is too long for external_id."}

        desc = (row.get("description") or "")[:255]
        if not row.get("operation_date"):
            return {"error": "Row is missing operation_date."}

        amount_usd = _decimal_from_row_field(row.get("amount_usd"), "amount_usd")
        if amount_usd is None:
            return {"error": "Row is missing or invalid amount_usd."}
        if amount_usd == 0:
            return {"error": "Transaction amount must not be zero."}

        magnitude = abs(amount_usd)
        if amount_usd < 0:
            direction = Direction.INCOME
            tx_type = TransactionType.CREDIT
        else:
            direction = Direction.EXPENSE
            tx_type = TransactionType.DEBIT

        amount_local = _decimal_from_row_field(row.get("amount_local"), "amount_local")
        currency = "USD"

        category = None
        if desc:
            inferred, desc_override = inferred_category_for_bsa(user, desc)
            category = inferred
            if desc_override:
                desc = desc_override[:255]

        ext_id = ref
        raw_safe = bsa_row_json_safe(row)

        statement_dt = _visa_statement_dt(row["operation_date"])

        tx, was_created = Transaction.objects.get_or_create(
            user=user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id=ext_id,
            defaults={
                "description": desc,
                "amount": magnitude,
                "currency": currency,
                "amount_local": amount_local,
                "exchange_rate": (
                    (amount_local / magnitude) if amount_local is not None else None
                ),
                "transaction_type": tx_type,
                "direction": direction,
                "category": category,
                "subcategory": None,
                "original_reference": ref[:255] or None,
                "is_installment": False,
                "raw_data": raw_safe,
                "imported_at": statement_dt,
                "status": TransactionStatus.CONFIRMED,
                "file_import": file_import,
                "visa_international_statement": visa_statement,
            },
        )
        if not was_created:
            return {"ok": "skipped", "instance": None}

        _persist_visa_created_dates_and_recurring_match(user, tx, statement_dt)
        return {"ok": "created", "instance": tx}
    except (KeyError, TypeError, ValueError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Visa Internacional row import failed")
        return {"error": str(exc)}
