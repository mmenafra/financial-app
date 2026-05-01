import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


def parse_bsa_amount(value):
    cleaned = (value or "").strip()
    if not cleaned:
        return None

    normalized = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount value: {value}") from exc


def parse_bsa_date(value):
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Date is required for each transaction row.")

    try:
        return datetime.strptime(cleaned, "%d%m%Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid date value: {value}") from exc


def parse_bsa_bank_statement(file_content):
    metadata = {}
    transactions = []

    for raw_line in file_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        logger.debug("Bank statement: processing line: %r", line[:200])

        if line.startswith(";"):
            meta_line = line[1:].strip()
            if ":" in meta_line:
                key, value = meta_line.split(":", 1)
                metadata[key.strip()] = value.strip()
            continue

        if line.lower().startswith("fecha;descripcion;"):
            continue

        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 6:
            if ";" in line and not line.startswith(";"):
                logger.warning(
                    "Bank statement: skipped line with < 6 fields: %r", line[:200]
                )
            continue

        transactions.append(
            {
                "date": parse_bsa_date(parts[0]),
                "description": parts[1],
                "document_number": parts[2],
                "debit": parse_bsa_amount(parts[3]),
                "credit": parse_bsa_amount(parts[4]),
                "balance": parse_bsa_amount(parts[5]),
            }
        )

    logger.info(
        "Bank statement: parsed metadata keys=%s transactions=%s",
        len(metadata),
        len(transactions),
    )
    return {"metadata": metadata, "transactions": transactions}
