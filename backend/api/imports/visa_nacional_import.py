"""Persist Visa Nacional (CLP PDF) parsed rows as Transaction records."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db.models import Q

from ..models import (
    Direction,
    FileImport,
    Source,
    Transaction,
    TransactionStatus,
    VisaNacionalStatement,
)
from ..recurring.match import apply_recurring_match_if_missing
from .bsa_import import bsa_row_json_safe
from .visa_internacional_import import (
    _decimal_from_row_field,
    _infer_desc_and_category,
    _resolve_visa_direction,
    _SkippedRow,
    _visa_statement_dt,
    transaction_date_from_iso,
    visa_skip_pago_en_efectivo,
)

logger = logging.getLogger(__name__)


def _parse_installment_parts(label: Any) -> tuple[int | None, int | None]:
    """Parse ``NN/NN`` from parser (e.g. ``06/12`` → current 6, total 12)."""
    if label is None:
        return None, None
    s = str(label).strip()
    if "/" not in s:
        return None, None
    parts = s.split("/", 1)
    if len(parts) != 2:
        return None, None
    try:
        cur = int(parts[0].strip(), 10)
        tot = int(parts[1].strip(), 10)
        if cur < 1 or tot < 1:
            return None, None
        return cur, tot
    except ValueError:
        return None, None


def sum_visa_nacional_parsed_expenses_clp(rows: list[dict]) -> Decimal:
    """Sum of CLP amounts for expense rows (positive ``amount``), matching import direction rules."""
    total = Decimal("0")
    for row in rows:
        if visa_skip_pago_en_efectivo(row.get("description")):
            continue
        amount = _decimal_from_row_field(row.get("amount"), "amount")
        if amount is not None and amount > 0:
            total += amount
    return total


def skipped_item_preview_from_nacional_row(row: dict) -> dict:
    """Minimal summary for import API when a Nacional row is skipped (duplicate or filtered)."""
    raw_desc = row.get("description")
    desc = (str(raw_desc).strip() if raw_desc is not None else "") or "(no description)"
    desc = desc[:255]
    amount_val = _decimal_from_row_field(row.get("amount"), "amount")
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
        "currency": "CLP",
        "direction": direction,
    }


def _handle_nacional_duplicate(user, ext_id: str, ref: str, cal_date) -> bool:
    """Return True and migrate external_id when a duplicate exists, else False."""
    duplicate = (
        Transaction.objects.filter(user=user, source=Source.CREDIT_CARD_NATIONAL)
        .filter(Q(external_id=ext_id) | Q(external_id=ref, transaction_date=cal_date))
        .first()
    )
    if duplicate is None:
        return False
    if duplicate.external_id == ref:
        duplicate.external_id = ext_id
        duplicate.save(update_fields=["external_id"])
    apply_recurring_match_if_missing(user, duplicate.pk)
    return True


def _resolve_nacional_installment(
    row: dict,
) -> tuple[bool, int | None, int | None, Decimal | None]:
    """Return (is_installment, current, total, amount) from the installment fields."""
    inst_cur, inst_tot = _parse_installment_parts(row.get("installment"))
    inst_amt = _decimal_from_row_field(
        row.get("installment_value"), "installment_value"
    )
    trivial = inst_cur == 1 and inst_tot == 1
    is_installment = inst_cur is not None and inst_tot is not None and not trivial
    return (
        is_installment,
        None if trivial else inst_cur,
        None if trivial else inst_tot,
        None if trivial else inst_amt,
    )


def import_visa_nacional_row(
    user,
    row: dict,
    file_import: FileImport | None = None,
    visa_statement: VisaNacionalStatement | None = None,
) -> dict:
    """
    Import one Visa Nacional parsed row.

    Returns:
        {"ok": "created", "instance": Transaction}
        {"ok": "skipped", "instance": None}
        {"error": "..."}
    """
    try:
        ref_raw = row.get("reference_code")
        ref = str(ref_raw).strip() if ref_raw is not None else ""
        if not ref:
            raise ValueError("Row is missing reference_code.")

        raw_desc = row.get("description")
        if visa_skip_pago_en_efectivo(raw_desc):
            raise _SkippedRow

        op_date_iso = row.get("operation_date")
        if not op_date_iso:
            raise ValueError("Row is missing operation_date.")

        ext_id = f"{ref}:{op_date_iso}"
        if len(ext_id) > 255:
            raise ValueError("Reference is too long for external_id.")

        amount_val = _decimal_from_row_field(row.get("amount"), "amount")
        if amount_val is None:
            raise ValueError("Row is missing or invalid amount.")
        if amount_val == 0:
            raise ValueError("Transaction amount must not be zero.")

        magnitude, direction, tx_type = _resolve_visa_direction(amount_val)
        desc, category = _infer_desc_and_category(user, raw_desc)
        is_installment, inst_cur, inst_tot, inst_amt = _resolve_nacional_installment(
            row
        )
        raw_safe = bsa_row_json_safe(row)
        statement_dt = _visa_statement_dt(op_date_iso)
        cal_date = transaction_date_from_iso(op_date_iso)

        if _handle_nacional_duplicate(user, ext_id, ref, cal_date):
            return {"ok": "skipped", "instance": None}

        tx = Transaction.objects.create(
            user=user,
            source=Source.CREDIT_CARD_NATIONAL,
            external_id=ext_id,
            description=desc,
            amount=magnitude,
            currency="CLP",
            amount_local=None,
            exchange_rate=None,
            transaction_type=tx_type,
            direction=direction,
            category=category,
            subcategory=None,
            original_reference=ref[:255] or None,
            is_installment=is_installment,
            installment_current=inst_cur,
            installment_total=inst_tot,
            installment_amount=inst_amt,
            raw_data=raw_safe,
            imported_at=statement_dt,
            transaction_date=cal_date,
            status=TransactionStatus.CONFIRMED,
            file_import=file_import,
            visa_nacional_statement=visa_statement,
        )

        apply_recurring_match_if_missing(user, tx.pk)
        return {"ok": "created", "instance": tx}
    except _SkippedRow:
        return {"ok": "skipped", "instance": None}
    except (KeyError, TypeError, ValueError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Visa Nacional row import failed")
        return {"error": str(exc)}
