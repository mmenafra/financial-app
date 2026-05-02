"""Persist Visa Internacional (USD PDF) parsed rows as Transaction records."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

from ..models import (
    Direction,
    FileImport,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
    VisaInternationalStatement,
)
from ..recurring.match import apply_recurring_match_if_missing
from .amounts import parse_chilean_decimal
from .bsa_import import bsa_row_json_safe, inferred_category_for_bsa

logger = logging.getLogger(__name__)


def _resolve_visa_direction(
    amount_val: Decimal,
) -> tuple[Decimal, "Direction", "TransactionType"]:
    """Return (magnitude, direction, tx_type) from a signed Visa amount."""
    magnitude = abs(amount_val)
    if amount_val < 0:
        return magnitude, Direction.INCOME, TransactionType.CREDIT
    return magnitude, Direction.EXPENSE, TransactionType.DEBIT


def _infer_desc_and_category(user, raw_desc) -> tuple[str, Any]:
    """Apply category inference and return (canonical_description, category_or_none)."""
    desc = (raw_desc or "")[:255]
    if desc:
        inferred, desc_override = inferred_category_for_bsa(user, desc)
        if desc_override:
            desc = desc_override[:255]
        return desc, inferred
    return desc, None


_VISA_SKIP_PAGO_EN_EFECTIVO = "PAGO EN EFECTIVO"


def visa_skip_pago_en_efectivo(description: str | None) -> bool:
    """Whether this Visa Nacional / Internacional description should not be imported."""
    if description is None:
        return False
    normalized = " ".join(str(description).strip().upper().split())
    return normalized == _VISA_SKIP_PAGO_EN_EFECTIVO


def transaction_date_from_iso(iso_date: str) -> date:
    """Calendar date from ISO ``YYYY-MM-DD`` (statement row date)."""
    return date.fromisoformat(iso_date)


def _visa_statement_dt(operation_date_iso: str) -> timezone.datetime:
    d = transaction_date_from_iso(operation_date_iso)
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
        if visa_skip_pago_en_efectivo(row.get("description")):
            continue
        amount_usd = _decimal_from_row_field(row.get("amount_usd"), "amount_usd")
        if amount_usd is not None and amount_usd > 0:
            total += amount_usd
    return total


def skipped_item_preview_from_internacional_row(row: dict) -> dict:
    """Minimal summary for import API when an Internacional row is skipped (duplicate or filtered)."""
    raw_desc = row.get("description")
    desc = (str(raw_desc).strip() if raw_desc is not None else "") or "(no description)"
    desc = desc[:255]
    amount_val = _decimal_from_row_field(row.get("amount_usd"), "amount_usd")
    if amount_val is None:
        magnitude = Decimal("0")
        direction = Direction.EXPENSE.value
    else:
        magnitude = abs(amount_val)
        direction = (
            Direction.INCOME.value if amount_val < 0 else Direction.EXPENSE.value
        )
    return {
        "description": desc,
        "amount": str(magnitude),
        "currency": "USD",
        "direction": direction,
    }


def _parse_internacional_ref(row: dict) -> str:
    """Return validated reference string, or raise ValueError."""
    ref_raw = row.get("reference")
    ref = str(ref_raw).strip() if ref_raw is not None else ""
    if not ref:
        raise ValueError("Row is missing reference.")
    if len(ref) > 255:
        raise ValueError("Reference is too long for external_id.")
    return ref


class _SkippedRow(Exception):
    """Raised when a row should be silently skipped (not an error)."""


def import_visa_internacional_row(
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
        ref = _parse_internacional_ref(row)
        raw_desc = row.get("description")
        if visa_skip_pago_en_efectivo(raw_desc):
            raise _SkippedRow

        if not row.get("operation_date"):
            raise ValueError("Row is missing operation_date.")

        amount_usd = _decimal_from_row_field(row.get("amount_usd"), "amount_usd")
        if amount_usd is None:
            raise ValueError("Row is missing or invalid amount_usd.")
        if amount_usd == 0:
            raise ValueError("Transaction amount must not be zero.")

        magnitude, direction, tx_type = _resolve_visa_direction(amount_usd)
        amount_local = _decimal_from_row_field(row.get("amount_local"), "amount_local")
        desc, category = _infer_desc_and_category(user, raw_desc)
        raw_safe = bsa_row_json_safe(row)
        statement_dt = _visa_statement_dt(row["operation_date"])

        tx, was_created = Transaction.objects.get_or_create(
            user=user,
            source=Source.CREDIT_CARD_INTERNATIONAL,
            external_id=ref,
            defaults={
                "description": desc,
                "amount": magnitude,
                "currency": "USD",
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
                "transaction_date": transaction_date_from_iso(row["operation_date"]),
                "status": TransactionStatus.CONFIRMED,
                "file_import": file_import,
                "visa_international_statement": visa_statement,
            },
        )
        apply_recurring_match_if_missing(user, tx.pk)
        if not was_created:
            return {"ok": "skipped", "instance": None}
        return {"ok": "created", "instance": tx}
    except _SkippedRow:
        return {"ok": "skipped", "instance": None}
    except (KeyError, TypeError, ValueError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Visa Internacional row import failed")
        return {"error": str(exc)}
