"""DRF views that proxy Mercado Pago Payments API for the frontend test page."""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from .client import MissingMercadoPagoTokenError, get_payment, search_payments


def _normalize_sdk_payload(raw: dict) -> tuple[int, dict | list]:
    """Return HTTP status code and JSON body from SDK result dict."""

    status_code = raw.get("status")
    response_body = raw.get("response")
    if status_code is None:
        # Defensive fallback if SDK shape changes
        return 200, raw
    if response_body is None:
        return int(status_code), {}
    if isinstance(response_body, list):
        return int(status_code), {"results": response_body}
    if isinstance(response_body, dict):
        return int(status_code), response_body
    return int(status_code), {"detail": str(response_body)}


class MercadoPagoTransactionListView(APIView):
    """List payments (search) for the authenticated user's app (server token)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if not (settings.MERCADOPAGO_ACCESS_TOKEN or "").strip():
            return Response(
                {"detail": "Mercado Pago access token is not configured."},
                status=503,
            )
        try:
            offset = int(request.query_params.get("offset", "0"))
        except (TypeError, ValueError):
            offset = 0
        try:
            limit = int(request.query_params.get("limit", "30"))
        except (TypeError, ValueError):
            limit = 30

        try:
            raw = search_payments(offset=offset, limit=limit)
        except MissingMercadoPagoTokenError as exc:
            return Response({"detail": str(exc)}, status=503)
        except Exception as exc:  # pylint: disable=broad-except
            return Response(
                {"detail": f"Mercado Pago request failed: {exc!s}"},
                status=502,
            )

        code, body = _normalize_sdk_payload(raw)
        return Response(body, status=code if code >= 400 else 200)


class MercadoPagoTransactionDetailView(APIView):
    """Single payment by id."""

    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id: str, *args, **kwargs):
        if not (settings.MERCADOPAGO_ACCESS_TOKEN or "").strip():
            return Response(
                {"detail": "Mercado Pago access token is not configured."},
                status=503,
            )
        if not payment_id or not str(payment_id).strip():
            return Response({"detail": "payment_id is required."}, status=400)

        try:
            raw = get_payment(payment_id)
        except MissingMercadoPagoTokenError as exc:
            return Response({"detail": str(exc)}, status=503)
        except Exception as exc:  # pylint: disable=broad-except
            return Response(
                {"detail": f"Mercado Pago request failed: {exc!s}"},
                status=502,
            )

        code, body = _normalize_sdk_payload(raw)
        return Response(body, status=code if code >= 400 else 200)
