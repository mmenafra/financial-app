"""
Parse Scotiabank Chile Visa Nacional credit card PDF statements.

Extracts only transaction rows from section II. DETALLE -> 2.PERÍODO ACTUAL.
Requires a text-based PDF (no OCR).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .amounts import parse_chilean_decimal
from .pdf_text import extract_text_from_pdf

logger = logging.getLogger(__name__)

_DATE_POSTING_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{4})\s*$")
_REFERENCE_RE = re.compile(r"^\d{6,}$")
# All $-amount tokens on a line (Chilean formatting)
_AMOUNT_TOKEN_RE = re.compile(r"\$\s*(-?[\d.,]+)")
_INSTALLMENT_TAIL_RE = re.compile(r"(\d{2}/\d{2})\s*\$\s*(-?[\d.,]+)\s*$")
# Billing range in período header: two full calendar dates (start end)
_TWO_FULL_DATES_IN_HEADER_RE = re.compile(
    r"\b(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\b"
)

_SECTION_START = "2.PERÍODO ACTUAL"
_SECTION_END_PREFIXES = (
    "3.CARGOS",
    "III.",
    "IV.",
)


def _norm_for_label_match(s: str) -> str:
    return (
        s.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def parse_monto_total_facturado_a_pagar_clp(full_text: str) -> Decimal | None:
    """
    Statement bill total from **Monto Total Facturado a Pagar** (Scotiabank Visa Nacional).

    Uses only a few lines after the label so unrelated ``$ 0`` (e.g. período anterior) is not
    picked up. Prefers ``$`` on the line containing **pagar**, then the max ``$`` amount in
    that window, then a plain Chilean number on the following line.
    """
    lines = full_text.splitlines()
    for i, line in enumerate(lines):
        n = _norm_for_label_match(line)
        if "monto total" not in n:
            continue
        local = lines[i : min(i + 5, len(lines))]
        joined = _norm_for_label_match(" ".join(local))
        if "facturado" not in joined or "a pagar" not in joined:
            continue
        for jl in local:
            if "pagar" in _norm_for_label_match(jl):
                line_amts: list[Decimal] = []
                for m in _AMOUNT_TOKEN_RE.finditer(jl):
                    try:
                        line_amts.append(_parse_chilean_amount(m.group(0)))
                    except ValueError:
                        continue
                if line_amts:
                    return line_amts[-1]
        window_amounts: list[Decimal] = []
        for jl in local:
            for m in _AMOUNT_TOKEN_RE.finditer(jl):
                try:
                    window_amounts.append(_parse_chilean_amount(m.group(0)))
                except ValueError:
                    continue
        if window_amounts:
            return max(window_amounts)
        for jl in local[1:]:
            seg = jl.strip()
            if not seg or _norm_for_label_match(seg).startswith("monto"):
                continue
            inner = seg.replace("$", "").strip()
            try:
                return parse_chilean_decimal(inner)
            except ValueError:
                continue
    return None


def _parse_chilean_amount(token: str) -> Decimal:
    return parse_chilean_decimal(token)


def _parse_amounts_from_line(
    line: str,
) -> tuple[list[Decimal], str | None, Decimal | None]:
    """
    Returns (all_amounts, installment_label, installment_value).
    installment_* set when line ends with 'NN/NN $ amount'.
    """
    amounts: list[Decimal] = []
    for m in _AMOUNT_TOKEN_RE.finditer(line):
        amounts.append(_parse_chilean_amount(m.group(0)))

    inst_label: str | None = None
    inst_value: Decimal | None = None
    m_tail = _INSTALLMENT_TAIL_RE.search(line)
    if m_tail and len(amounts) >= 2:
        inst_label = m_tail.group(1)
        inst_value = _parse_chilean_amount(m_tail.group(2))

    return amounts, inst_label, inst_value


def _operation_date_to_iso(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid operation date: {date_str!r}") from exc


def extract_periodo_actual_header_text(full_text: str) -> str:
    """
    Lines after ``2.PERÍODO ACTUAL`` until ``1.TOTAL OPERACIONES`` / section end /
    first transaction date line (``DD/MM/YYYY 0903``).

    Used to read the printed billing date pair (period end = later date).
    """
    detalle_idx = full_text.find("II. DETALLE")
    slice_from = full_text[detalle_idx:] if detalle_idx != -1 else full_text
    idx = slice_from.find(_SECTION_START)
    if idx == -1:
        return ""
    chunk = slice_from[idx + len(_SECTION_START) :]
    lines_out: list[str] = []
    for line in chunk.splitlines():
        stripped = line.strip()
        if "1.TOTAL OPERACIONES" in stripped or stripped.startswith("1.TOTAL OPERACIONES"):
            break
        if any(stripped.startswith(p) for p in _SECTION_END_PREFIXES):
            break
        if _DATE_POSTING_RE.search(stripped):
            break
        lines_out.append(line)
    return "\n".join(lines_out)


def parse_visa_nacional_period_end(full_text: str, fallback: date | None) -> date:
    """
    Closing date from the pair printed under ``2.PERÍODO ACTUAL`` (later of the two dates).

    Falls back to ``fallback`` (e.g. max operation date) when the PDF omits the pair.
    """
    header = extract_periodo_actual_header_text(full_text)
    m = _TWO_FULL_DATES_IN_HEADER_RE.search(header)
    if m:
        d1 = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        d2 = datetime.strptime(m.group(2), "%d/%m/%Y").date()
        return max(d1, d2)
    if fallback is not None:
        logger.warning(
            "Visa Nacional: no date pair after 2.PERÍODO ACTUAL; using fallback period_end=%s",
            fallback,
        )
        return fallback
    raise ValueError(
        "Could not determine Visa Nacional billing period end from PDF header."
    )


def parse_visa_nacional_total_operaciones_clp(periodo_block: str) -> Decimal | None:
    """Amount on ``1.TOTAL OPERACIONES`` line (first $ token), Chilean formatting."""
    for line in periodo_block.splitlines():
        stripped = line.strip()
        if "1.TOTAL OPERACIONES" not in stripped:
            continue
        amounts: list[Decimal] = []
        for m in _AMOUNT_TOKEN_RE.finditer(line):
            try:
                amounts.append(_parse_chilean_amount(m.group(0)))
            except ValueError:
                continue
        if amounts:
            return amounts[0]
    return None


def _sum_positive_row_amounts_clp(rows: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        raw = row.get("amount")
        if raw is None:
            continue
        try:
            amt = parse_chilean_decimal(str(raw))
        except ValueError:
            amt = Decimal(str(raw))
        if amt > 0:
            total += amt
    return total


def extract_periodo_actual_block(text: str) -> str:
    """
    Return text from the first ``2.PERÍODO ACTUAL`` until section 3 / III / IV.
    """
    detalle_idx = text.find("II. DETALLE")
    slice_from = text[detalle_idx:] if detalle_idx != -1 else text

    idx = slice_from.find(_SECTION_START)
    if idx == -1:
        raise ValueError("Could not find section '2.PERÍODO ACTUAL' in PDF text.")

    start = idx + len(_SECTION_START)
    rest = slice_from[start:]

    lines_out: list[str] = []
    for line in rest.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(p) for p in _SECTION_END_PREFIXES):
            break
        lines_out.append(line)
    return "\n".join(lines_out)


def parse_transactions_from_periodo_text(block: str) -> list[dict[str, Any]]:
    """
    Parse transaction rows from the periodo-actual block (plain text).

    Each transaction: date+posting line, reference line (digits), description line with $.
    """
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    transactions: list[dict[str, Any]] = []
    i = 0
    skip_until_after_total = True

    while i < len(lines):
        line = lines[i]

        if skip_until_after_total:
            if "1.TOTAL OPERACIONES" in line or line.startswith("1.TOTAL OPERACIONES"):
                skip_until_after_total = False
            i += 1
            continue

        m = _DATE_POSTING_RE.search(line)
        if not m:
            i += 1
            continue

        date_idx = i
        op_date_raw, posting_code = m.group(1), m.group(2)

        if date_idx + 1 >= len(lines):
            break
        ref_line = lines[date_idx + 1]
        if not _REFERENCE_RE.match(ref_line):
            i = date_idx + 1
            continue

        reference_code = ref_line

        if date_idx + 2 >= len(lines):
            break
        desc_line = lines[date_idx + 2]
        if "$" not in desc_line:
            i = date_idx + 1
            continue

        amounts, inst_label, inst_value = _parse_amounts_from_line(desc_line)
        if not amounts:
            i = date_idx + 1
            continue

        # Description: text before first $ token
        first_dollar = desc_line.find("$")
        description = desc_line[:first_dollar].strip()

        entry: dict[str, Any] = {
            "operation_date": _operation_date_to_iso(op_date_raw),
            "posting_code": posting_code,
            "reference_code": reference_code,
            "description": description,
            "amount": str(amounts[0]),
        }
        if len(amounts) > 1:
            entry["total_to_pay"] = str(amounts[1])
        if inst_label is not None and inst_value is not None:
            entry["installment"] = inst_label
            entry["installment_value"] = str(inst_value)

        transactions.append(entry)
        i = date_idx + 3

    return transactions


def parse_visa_nacional_statement_text(full_text: str) -> dict[str, Any]:
    """Parse PDF text: transactions, statement ``period_end``, and ``total_operaciones`` from PDF."""
    block = extract_periodo_actual_block(full_text)
    logger.debug("Visa Nacional: periodo-actual block length=%s characters", len(block))
    transactions = parse_transactions_from_periodo_text(block)
    if not transactions:
        raise ValueError("No transactions found in '2.PERÍODO ACTUAL' section.")

    op_dates = [date.fromisoformat(str(t["operation_date"])) for t in transactions]
    fallback_end = max(op_dates)
    period_end = parse_visa_nacional_period_end(full_text, fallback=fallback_end)

    total_facturado = parse_monto_total_facturado_a_pagar_clp(full_text)
    total_pdf = total_facturado
    if total_pdf is None:
        total_pdf = parse_visa_nacional_total_operaciones_clp(block)
    if total_pdf is not None:
        total_amount = total_pdf
    else:
        logger.warning(
            "Visa Nacional: missing Monto Total Facturado a Pagar and 1.TOTAL OPERACIONES; "
            "summing positive row amounts.",
        )
        total_amount = _sum_positive_row_amounts_clp(transactions)

    logger.info(
        "Visa Nacional: parsed %s transactions, period_end=%s total=%s",
        len(transactions),
        period_end,
        total_amount,
    )
    return {
        "transactions": transactions,
        "period_end": period_end.isoformat(),
        "total_operaciones": str(total_amount),
    }


def parse_visa_nacional_statement_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    """Extract text from PDF bytes and parse Visa Nacional transactions."""
    logger.debug("Visa Nacional: parsing PDF, size=%s bytes", len(pdf_bytes))
    text = extract_text_from_pdf(pdf_bytes)
    if not text or not text.strip():
        raise ValueError("PDF contains no extractable text (may be image-only).")
    return parse_visa_nacional_statement_text(text)
