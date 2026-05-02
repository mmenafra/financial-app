"""DRF views that proxy Mercado Pago / MercadoLibre APIs for the frontend."""

from __future__ import annotations

import requests as http_requests
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from .client import (
    MissingMercadoPagoTokenError,
    get_ml_items,
    get_payment,
    search_payments,
)


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


class MercadoLibreItemsView(APIView):
    """Proxy GET https://api.mercadolibre.com/items?ids=… using the server-side MP token."""

    permission_classes = [IsAuthenticated]

    def _validate(self, request) -> tuple[list[str] | None, Response | None]:
        """Return (item_ids, None) on success or (None, error_response) on failure."""
        if not (settings.MERCADOPAGO_ACCESS_TOKEN or "").strip():
            return None, Response(
                {"detail": "Mercado Pago access token is not configured."}, status=503
            )
        ids_param = request.query_params.get("ids", "").strip()
        item_ids = [i.strip() for i in ids_param.split(",") if i.strip()]
        if not item_ids:
            return None, Response(
                {"detail": "ids query parameter is required."}, status=400
            )
        return item_ids, None

    def get(self, request, *args, **kwargs):
        item_ids, err = self._validate(request)
        if err is not None:
            return err

        try:
            results = get_ml_items(item_ids)
        except MissingMercadoPagoTokenError as exc:
            return Response({"detail": str(exc)}, status=503)
        except http_requests.HTTPError:
            # All auth strategies exhausted — return empty list so the frontend
            # falls back to displaying item IDs with constructed ML links.
            return Response([], status=200)
        except Exception as exc:  # pylint: disable=broad-except
            return Response(
                {"detail": f"MercadoLibre items request failed: {exc!s}"}, status=502
            )

        return Response(results)


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
