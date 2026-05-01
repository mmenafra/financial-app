"""Thin wrapper around the official Mercado Pago Python SDK for payments."""

from __future__ import annotations

import mercadopago
from django.conf import settings


class MissingMercadoPagoTokenError(RuntimeError):
    """Raised when MERCADOPAGO_ACCESS_TOKEN is missing or blank."""


def _access_token_or_raise() -> str:
    token = (settings.MERCADOPAGO_ACCESS_TOKEN or "").strip()
    if not token:
        raise MissingMercadoPagoTokenError(
            "Mercado Pago access token is not configured."
        )
    return token


def search_payments(*, offset: int, limit: int) -> dict:
    """GET /v1/payments/search via SDK (newest payments first).

    Pagination: Mercado Pago allows limit up to 50 and offset up to 10000.
    """

    sdk = mercadopago.SDK(_access_token_or_raise())
    safe_limit = max(1, min(int(limit), 50))
    safe_offset = max(0, min(int(offset), 10_000))
    return sdk.payment().search(
        {
            "sort": "date_created",
            "criteria": "desc",
            "offset": safe_offset,
            "limit": safe_limit,
        }
    )


def get_payment(payment_id: str) -> dict:
    """GET /v1/payments/{id} via SDK."""

    sdk = mercadopago.SDK(_access_token_or_raise())
    payment_id_clean = str(payment_id).strip()
    return sdk.payment().get(payment_id_clean)
