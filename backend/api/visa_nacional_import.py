"""Persist Visa Nacional (CLP PDF) parsed rows as Transaction records."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from .bsa_import import bsa_row_json_safe, inferred_category_for_bsa
from .models import (
    Direction,
    FileImport,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
    VisaNacionalStatement,
)
from .recurring_match import apply_recurring_match_if_missing
from .visa_internacional_import import (
    _decimal_from_row_field,
    _persist_visa_created_dates_and_recurring_match,
    _visa_statement_dt,
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


def import_visa_nacional_row(  # pylint: disable=too-many-return-statements,too-many-branches  # noqa: C901
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
            return {"error": "Row is missing reference_code."}
        if len(ref) > 255:
            return {"error": "Reference is too long for external_id."}

        raw_desc = row.get("description")
        if visa_skip_pago_en_efectivo(raw_desc):
            return {"ok": "skipped", "instance": None}

        desc = (raw_desc or "")[:255]
        if not row.get("operation_date"):
            return {"error": "Row is missing operation_date."}

        amount_val = _decimal_from_row_field(row.get("amount"), "amount")
        if amount_val is None:
            return {"error": "Row is missing or invalid amount."}
        if amount_val == 0:
            return {"error": "Transaction amount must not be zero."}

        magnitude = abs(amount_val)
        if amount_val < 0:
            direction = Direction.INCOME
            tx_type = TransactionType.CREDIT
        else:
            direction = Direction.EXPENSE
            tx_type = TransactionType.DEBIT

        category = None
        if desc:
            inferred, desc_override = inferred_category_for_bsa(user, desc)
            category = inferred
            if desc_override:
                desc = desc_override[:255]

        inst_cur, inst_tot = _parse_installment_parts(row.get("installment"))
        inst_amt = _decimal_from_row_field(
            row.get("installment_value"), "installment_value"
        )
        trivial_one_of_one = inst_cur == 1 and inst_tot == 1
        is_installment = (
            inst_cur is not None
            and inst_tot is not None
            and not trivial_one_of_one
        )
        inst_cur_save = None if trivial_one_of_one else inst_cur
        inst_tot_save = None if trivial_one_of_one else inst_tot
        inst_amt_save = None if trivial_one_of_one else inst_amt

        ext_id = ref
        raw_safe = bsa_row_json_safe(row)

        statement_dt = _visa_statement_dt(row["operation_date"])

        tx, was_created = Transaction.objects.get_or_create(
            user=user,
            source=Source.CREDIT_CARD_NATIONAL,
            external_id=ext_id,
            defaults={
                "description": desc,
                "amount": magnitude,
                "currency": "CLP",
                "amount_local": None,
                "exchange_rate": None,
                "transaction_type": tx_type,
                "direction": direction,
                "category": category,
                "subcategory": None,
                "original_reference": ref[:255] or None,
                "is_installment": is_installment,
                "installment_current": inst_cur_save,
                "installment_total": inst_tot_save,
                "installment_amount": inst_amt_save,
                "raw_data": raw_safe,
                "imported_at": statement_dt,
                "status": TransactionStatus.CONFIRMED,
                "file_import": file_import,
                "visa_nacional_statement": visa_statement,
            },
        )
        if not was_created:
            apply_recurring_match_if_missing(user, tx.pk)
            return {"ok": "skipped", "instance": None}

        _persist_visa_created_dates_and_recurring_match(user, tx, statement_dt)
        return {"ok": "created", "instance": tx}
    except (KeyError, TypeError, ValueError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Visa Nacional row import failed")
        return {"error": str(exc)}
