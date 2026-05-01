"""Persist Banco Santander-style (.dat) bank statement rows as Transaction records."""

import logging
from datetime import date, datetime, time
from decimal import Decimal

from django.utils import timezone

from ..models import (
    Category,
    Direction,
    FileImport,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)

logger = logging.getLogger(__name__)


def bsa_row_json_safe(row: dict) -> dict:
    """JSONField cannot store Decimal; persist amounts as strings."""
    out = {}
    for key, val in row.items():
        if isinstance(val, Decimal):
            out[key] = str(val)
        else:
            out[key] = val
    return out


def bsa_row_external_id(row: dict) -> str:
    debit = row.get("debit")
    credit = row.get("credit")
    amount = debit if debit is not None else credit
    amount_str = str(amount) if amount is not None else ""
    desc = (row.get("description") or "")[:100]
    return f"{row.get('date', '')}|{row.get('document_number', '')}|{amount_str}|{desc}"


def bsa_statement_dt(iso_date: str) -> datetime:
    d = date.fromisoformat(iso_date)
    dt = datetime.combine(d, time.min)
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def _normalize_description(description: str) -> str:
    return " ".join((description or "").split())


_MAX_INFERENCE_SCAN = 2000


def inferred_category_for_bsa(user, description: str):
    """Match normalized description against prior categorized rows (recent-first).

    Returns (category, description_to_use). When a prior row matches, description_to_use
    is that row's stored description so imports reuse the user's corrected wording.
    """

    norm = _normalize_description(description[:255])
    if not norm:
        return None, None
    scanned = 0
    for tx in (
        Transaction.objects.filter(user=user, category__isnull=False)
        .order_by("-transaction_date", "-created_at")
        .iterator(chunk_size=200)
    ):
        if scanned >= _MAX_INFERENCE_SCAN:
            break
        scanned += 1
        if _normalize_description(tx.description) != norm:
            continue
        category = Category.objects.filter(pk=tx.category_id, user=user).first()
        desc_from_prior = (tx.description or "")[:255] or description[:255]
        return category, desc_from_prior
    return None, None


class _BsaAmountError(ValueError):
    """Raised when debit/credit fields are invalid."""


def _resolve_bsa_amount(
    row: dict,
) -> tuple[Decimal, Direction, TransactionType]:
    """Return (amount, direction, tx_type) or raise _BsaAmountError."""
    debit = row.get("debit")
    credit = row.get("credit")
    if debit is not None and credit is not None:
        raise _BsaAmountError(
            "Row has both debit and credit; only one is allowed per row."
        )
    if debit is None and credit is None:
        raise _BsaAmountError(
            "Row has neither debit nor credit (no transaction amount)."
        )
    if debit is not None:
        amount, direction, tx_type = debit, Direction.EXPENSE, TransactionType.DEBIT
    else:
        amount, direction, tx_type = credit, Direction.INCOME, TransactionType.CREDIT
    if amount <= 0:
        raise _BsaAmountError("Transaction amount must be positive.")
    return amount, direction, tx_type


def import_bsa_row(user, row: dict, file_import: FileImport | None = None) -> dict:
    """
    Import one BSA-parsed row. Returns one of:
    {"ok": "created", "instance": Transaction}
    {"ok": "skipped", "instance": None}
    {"error": "..."}
    """
    try:
        # _resolve_bsa_amount raises _BsaAmountError (a ValueError subclass) on invalid input.
        amount, direction, tx_type = _resolve_bsa_amount(row)
        if not row.get("date"):
            raise ValueError("Row is missing date.")
        ext_id = bsa_row_external_id(row)
        if len(ext_id) > 255:
            raise ValueError("Could not build external_id: row data too long.")
        desc = (row.get("description") or "")[:255]
        category = None
        if desc:
            category, desc_override = inferred_category_for_bsa(user, desc)
            if desc_override:
                desc = desc_override
        statement_dt = bsa_statement_dt(row["date"])
        tx, was_created = Transaction.objects.get_or_create(
            user=user,
            source=Source.BANK_ACCOUNT,
            external_id=ext_id,
            defaults={
                "description": desc,
                "amount": amount,
                "currency": "CLP",
                "amount_local": None,
                "exchange_rate": None,
                "transaction_type": tx_type,
                "direction": direction,
                "category": category,
                "subcategory": None,
                "original_reference": (row.get("document_number") or "")[:255] or None,
                "is_installment": False,
                "raw_data": bsa_row_json_safe(row),
                "imported_at": statement_dt,
                "transaction_date": date.fromisoformat(row["date"]),
                "status": TransactionStatus.CONFIRMED,
                "file_import": file_import,
            },
        )
        if not was_created:
            return {"ok": "skipped", "instance": None}
        return {"ok": "created", "instance": tx}
    except (KeyError, TypeError, ValueError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("BSA row import failed")
        return {"error": str(exc)}
