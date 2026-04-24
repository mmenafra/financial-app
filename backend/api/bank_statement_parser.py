from datetime import datetime
from decimal import Decimal, InvalidOperation


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

    return {"metadata": metadata, "transactions": transactions}
