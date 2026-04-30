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
_LINE_COUNTRY_TOKEN_RE = re.compile(r"^[A-Z]{2}$")
# OCR sometimes glues UY (Uruguay) to the previous token (e.g. ESTUY). Restrict fused splits to
# unlikely merchant endings by requiring an uppercase ASCII stem of length >= 3 (avoids BU+UY).
_FUSED_COUNTRY_SUFFIXES = frozenset({"UY"})
# Merchant lines often append settlement location before country; strip longest match first.
_LOCATION_SUFFIXES: tuple[str, ...] = (
    "PUNTA DEL ESTE",
    "PUNTA DEL EST",
    "MONTEVIDEO",
)


def _parse_full_date(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%Y").date()


def extract_billing_period(text: str) -> tuple[date, date]:
    """First two full dates after II. DETALLE (period from / to)."""
    pos = text.find(_DETALLE)
    slice_start = pos if pos != -1 else 0
    chunk = text[slice_start : slice_start + 4000]
    found = _DATE_FULL_RE.findall(chunk)
    logger.info("Found dates: %s", found)
    if len(found) < 2:
        raise ValueError("Could not find billing period (two full dates) in PDF text.")
    a, b = _parse_full_date(found[0]), _parse_full_date(found[1])
    if a <= b:
        return a, b
    return b, a


def resolve_dd_mm_in_period(day_month: str, period_from: date, period_to: date) -> str:
    """Map DD/MM to an ISO date: prefer a day inside the billing window, else closest valid date."""
    day_s, m_s = day_month.split("/")
    d, m_ = int(day_s), int(m_s)
    candidates: list[date] = []
    for y in range(period_from.year - 1, period_to.year + 2):
        try:
            candidates.append(date(y, m_, d))
        except ValueError:
            continue
    if not candidates:
        raise ValueError(f"Invalid day/month {day_month!r}.")

    in_period = [c for c in candidates if period_from <= c <= period_to]
    if in_period:
        return min(in_period).isoformat()

    def days_from_billing_window(c: date) -> int:
        if c < period_from:
            return (period_from - c).days
        if c > period_to:
            return (c - period_to).days
        return 0

    best = min(candidates, key=lambda c: (days_from_billing_window(c), c))
    return best.isoformat()


def _pop_trailing_amount(s: str) -> tuple[str, str] | None:
    m = _TRAILING_AMT.search(s)
    if not m:
        return None
    return s[: m.start()].rstrip(), m.group(1)


def _try_split_fused_country_last_word(word: str) -> tuple[str, str | None]:
    """
    If ``word`` ends with a fused country suffix (e.g. ESTUY → EST + UY), return stem and code.

    Keeps false positives low: suffix whitelist and stem must be ASCII uppercase with length >= 3.
    """
    if len(word) < 5:
        return word, None
    cc = word[-2:]
    if cc not in _FUSED_COUNTRY_SUFFIXES:
        return word, None
    stem = word[:-2]
    if not stem.isascii() or not stem.isupper():
        return word, None
    if len(stem) < 3:
        return word, None
    return stem, cc


def _extract_country_and_merchant_line(  # pylint: disable=too-many-return-statements
    rest: str,
) -> tuple[str, str | None]:
    """Split trailing ISO-like country token from operation text (handles fused ESTUY-style OCR)."""
    rest = rest.strip()
    if not rest:
        return "", None
    parts = rest.rsplit(None, 1)
    if len(parts) == 1:
        word = parts[0]
        if _LINE_COUNTRY_TOKEN_RE.fullmatch(word):
            return "", word
        stem, cc = _try_split_fused_country_last_word(word)
        if cc:
            return stem, cc
        return rest, None
    prefix, last = parts[0].strip(), parts[1].strip()
    if _LINE_COUNTRY_TOKEN_RE.fullmatch(last):
        return prefix, last
    stem, cc = _try_split_fused_country_last_word(last)
    if cc:
        return f"{prefix} {stem}".strip(), cc
    return rest, None


def _strip_trailing_locations(merchant_line: str) -> tuple[str, str | None]:
    """
    Remove trailing settlement city phrases (before country was stripped).

    Returns ``(description, city_or_none)``. If stripping would erase all text, returns the original
    line with ``city`` ``None``.
    """
    original = merchant_line.strip()
    if not original:
        return original, None
    chunks: list[str] = []
    work = original
    while True:
        matched = False
        upper_work = work.upper()
        for phrase in _LOCATION_SUFFIXES:
            p = phrase.upper()
            if not upper_work.endswith(p):
                continue
            idx = len(work) - len(p)
            if idx > 0 and work[idx - 1] != " ":
                continue
            chunks.insert(0, work[idx:])
            work = work[:idx].rstrip()
            matched = True
            break
        if not matched:
            break
    city = " ".join(chunks) if chunks else None
    final_desc = work.strip()
    if not final_desc:
        return original, None
    return final_desc, city


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
    merchant_line, country = _extract_country_and_merchant_line(rest)
    description, city = _strip_trailing_locations(merchant_line)
    for amt in (a1, a2):
        parse_chilean_decimal(amt)  # validate

    return {
        "description": description,
        "country": country,
        "city": city,
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
    return {
        "period_from": p_from.isoformat(),
        "period_to": p_to.isoformat(),
        "transactions": transactions,
    }


def parse_visa_internacional_statement_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    logger.debug("Visa Internacional: parsing PDF, size=%s bytes", len(pdf_bytes))
    text = extract_text_from_pdf(pdf_bytes)
    if not text or not text.strip():
        raise ValueError("PDF contains no extractable text (may be image-only).")
    return parse_visa_internacional_statement_text(text)
