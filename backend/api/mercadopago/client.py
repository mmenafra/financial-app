"""Thin wrapper around the official Mercado Pago Python SDK for payments."""

from __future__ import annotations

import mercadopago
import requests

from django.conf import settings

ML_ITEMS_URL = "https://api.mercadolibre.com/items"
ML_ITEM_URL = "https://api.mercadolibre.com/items/{item_id}"


class MissingMercadoPagoTokenError(RuntimeError):
    """Raised when MERCADOPAGO_ACCESS_TOKEN is missing or blank."""


def _access_token_or_raise() -> str:
    token = (settings.MERCADOPAGO_ACCESS_TOKEN or "").strip()
    if not token:
        raise MissingMercadoPagoTokenError(
            "Mercado Pago access token is not configured."
        )
    return token


def search_payments(
    *,
    offset: int,
    limit: int,
    begin_date: str | None = None,
    end_date: str | None = None,
    range_field: str = "date_created",
) -> dict:
    """GET /v1/payments/search via SDK (newest payments first).

    When ``begin_date`` and ``end_date`` are set (ISO-8601), ``range_field`` must
    be a valid MP ``range`` value (e.g. ``dateCreated``/``date_created`` per SDK).

    Pagination: Mercado Pago allows limit up to 50 and offset up to 10000.
    """

    sdk = mercadopago.SDK(_access_token_or_raise())
    safe_limit = max(1, min(int(limit), 50))
    safe_offset = max(0, min(int(offset), 10_000))
    filters: dict = {
        "sort": "date_created",
        "criteria": "desc",
        "offset": safe_offset,
        "limit": safe_limit,
    }
    if begin_date and end_date:
        filters["range"] = range_field
        filters["begin_date"] = begin_date
        filters["end_date"] = end_date
    return sdk.payment().search(filters)


def get_payment(payment_id: str) -> dict:
    """GET /v1/payments/{id} via SDK."""

    sdk = mercadopago.SDK(_access_token_or_raise())
    payment_id_clean = str(payment_id).strip()
    return sdk.payment().get(payment_id_clean)


def get_ml_items(item_ids: list[str]) -> list[dict]:
    """Fetch ML item details via the batch endpoint.

    Per ML documentation, basic public item data does not require auth.
    We try without auth first; if the response is 401/403 we retry once
    with the MP/ML access token (same credential, different scope path).

    Returns the [{code, body}] list from the ML batch endpoint.
    Raises requests.HTTPError if both attempts fail.
    """

    safe_ids = [str(i).strip() for i in item_ids if str(i).strip()]
    if not safe_ids:
        return []

    ids_str = ",".join(safe_ids)

    # Attempt 1: no auth (public access as documented)
    resp = requests.get(ML_ITEMS_URL, params={"ids": ids_str}, timeout=10)
    if resp.status_code not in (401, 403):
        resp.raise_for_status()
        return resp.json()

    # Attempt 2: with Bearer token on batch endpoint
    token = _access_token_or_raise()
    resp = requests.get(
        ML_ITEMS_URL,
        params={"ids": ids_str},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if resp.status_code not in (401, 403):
        resp.raise_for_status()
        return resp.json()

    # Attempt 3: fall back to individual requests (single-item endpoint, no auth)
    results = []
    for item_id in safe_ids:
        r = requests.get(
            ML_ITEM_URL.format(item_id=item_id),
            timeout=10,
        )
        code = r.status_code
        body = r.json() if code == 200 else {}
        results.append({"code": code, "body": body})
    return results
