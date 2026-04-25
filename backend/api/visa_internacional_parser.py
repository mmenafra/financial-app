"""
Parse Scotiabank Chile Visa Internacional (USD) credit card PDF statements.

Extracts rows from **2. INFORMACIÓN DE TRANSACCIONES** (text-based PDF only).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from .amounts import parse_chilean_decimal
from .pdf_text import extract_text_from_pdf

logger = logging.getLogger(__name__)

_MARK_START = "2. INFORMACIÓN DE TRANSACCIONES"
_DETALLE = "II. DETALLE"
_DATE_FULL_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
_TX_START_RE = re.compile(r"^(\d{18})\s+(\d{2}/\d{2})(?:\s+|$)(.*)$")
# Trailing amount: thousands with dots + comma, or simple comma decimals
_TRAILING_AMT = re.compile(r"(-?(?:\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}))\s*$")


def _parse_full_date(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%Y").date()


def extract_billing_period(text: str) -> tuple[date, date]:
    """First two full dates after II. DETALLE (period from / to)."""
    pos = text.find(_DETALLE)
    slice_start = pos if pos != -1 else 0
    chunk = text[slice_start : slice_start + 4000]
    found = _DATE_FULL_RE.findall(chunk)
    if len(found) < 2:
        raise ValueError("Could not find billing period (two full dates) in PDF text.")
    a, b = _parse_full_date(found[0]), _parse_full_date(found[1])
    if a <= b:
        return a, b
    return b, a


def resolve_dd_mm_in_period(day_month: str, period_from: date, period_to: date) -> str:
    day_s, m_s = day_month.split("/")
    d, m_ = int(day_s), int(m_s)
    for y in range(period_from.year - 1, period_to.year + 2):
        try:
            candidate = date(y, m_, d)
        except ValueError:
            continue
        if period_from <= candidate <= period_to:
            return candidate.isoformat()
    raise ValueError(
        f"Could not resolve {day_month!r} within the billing period "
        f"{period_from}–{period_to}."
    )


def _pop_trailing_amount(s: str) -> tuple[str, str] | None:
    m = _TRAILING_AMT.search(s)
    if not m:
        return None
    return s[: m.start()].rstrip(), m.group(1)


def parse_transaction_line_body(body: str) -> dict[str, Any] | None:
    """
    Parse the text after 18-digit ref and DD/MM (rest of line(s), no ref/date prefix).
    Returns dict with amount strings and description, or None.
    """
    s = (body or "").strip()
    if not s:
        return None
    t = _pop_trailing_amount(s)
    if t is None:
        return None
    before2, a2 = t[0], t[1]
    t1 = _pop_trailing_amount(before2)
    if t1 is None:
        return None
    rest, a1 = t1[0], t1[1]
    if not rest:
        return None
    # Country = last word if exactly two A–Z; else no country (e.g. PAGO EN EFECTIVO)
    head = rest
    rsplit = head.rsplit(" ", 1)
    if len(rsplit) == 2 and re.fullmatch(r"[A-Z]{2}", rsplit[1]):
        country, description = rsplit[1], rsplit[0].strip()
    else:
        country, description = None, head.strip()
    for amt in (a1, a2):
        parse_chilean_decimal(amt)  # validate
    return {
        "description": description,
        "country": country,
        "city": None,
        "amount_local": str(parse_chilean_decimal(a1)),
        "amount_usd": str(parse_chilean_decimal(a2)),
    }


def _extract_transacciones_block(text: str) -> str:
    start = text.find(_MARK_START)
    if start == -1:
        raise ValueError(
            "Could not find '2. INFORMACIÓN DE TRANSACCIONES' in PDF text."
        )
    return text[start:]


def _line_starts_new_tx(line: str) -> bool:
    return bool(_TX_START_RE.match(line.strip()))


def _should_skip_line(line: str) -> bool:
    st = line.strip()
    if not st:
        return True
    return bool(
        st == _MARK_START
        or st.startswith(_MARK_START)
        or st.startswith("00/00")
        or st.startswith("Número Referencia")
        or st.startswith("Internacional")
        or st.startswith("Descripción Operación")
        or st.startswith("Descripción")
        or st == "Moneda"
        or st
        in (
            "Fecha",
            "Operación",
            "Monto",
            "US$",
            "Origen",
        )
        or re.match(r"^--\s*\d+\s+of\s+\d+\s*--$", st)
    )


def parse_transactions_in_block(
    block_text: str, period_from: date, period_to: date
) -> list[dict[str, Any]]:
    lines = [ln.rstrip() for ln in block_text.splitlines()]
    transactions: list[dict[str, Any]] = []
    i = 0
    n = len(lines)

    while i < n:
        s = lines[i].strip()
        if _should_skip_line(s):
            i += 1
            continue
        m = _TX_START_RE.match(s)
        if not m:
            i += 1
            continue
        ref, ddmm, part = m.group(1), m.group(2), (m.group(3) or "").strip()
        body: str = part
        j = i + 1
        if parse_transaction_line_body(body) is None:
            while j < n:
                nxt = lines[j].strip()
                if _line_starts_new_tx(nxt) or nxt.startswith("00/00"):
                    break
                if not nxt:
                    j += 1
                    continue
                body = f"{body} {nxt}".strip() if body else nxt
                j += 1
                if parse_transaction_line_body(body) is not None:
                    break
        else:
            j = i + 1
        parsed = parse_transaction_line_body(body)
        if parsed is None:
            logger.warning(
                "Visa Internacional: could not parse transaction line ref=%r body=%r",
                ref,
                (body or "")[:200],
            )
            i += 1
            continue
        op_iso = resolve_dd_mm_in_period(ddmm, period_from, period_to)
        entry: dict[str, Any] = {
            "reference": ref,
            "operation_date": op_iso,
            "description": parsed["description"],
            "city": parsed["city"],
            "country": parsed["country"],
            "amount_local": parsed["amount_local"],
            "amount_usd": parsed["amount_usd"],
        }
        transactions.append(entry)
        i = j
    return transactions


def parse_visa_internacional_statement_text(full_text: str) -> dict[str, Any]:
    p_from, p_to = extract_billing_period(full_text)
    logger.info(
        "Visa Internacional: billing period %s to %s",
        p_from.isoformat(),
        p_to.isoformat(),
    )
    block = _extract_transacciones_block(full_text)
    transactions = parse_transactions_in_block(block, p_from, p_to)
    if not transactions:
        raise ValueError(
            "No transactions found in '2. INFORMACIÓN DE TRANSACCIONES' section."
        )
    logger.info("Visa Internacional: parsed %s transactions", len(transactions))
    return {"transactions": transactions}


def parse_visa_internacional_statement_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    logger.debug("Visa Internacional: parsing PDF, size=%s bytes", len(pdf_bytes))
    text = extract_text_from_pdf(pdf_bytes)
    if not text or not text.strip():
        raise ValueError("PDF contains no extractable text (may be image-only).")
    return parse_visa_internacional_statement_text(text)
