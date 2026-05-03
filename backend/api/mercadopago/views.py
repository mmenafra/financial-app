"""DRF views that proxy Mercado Pago / MercadoLibre APIs for the frontend."""

from __future__ import annotations

import requests as http_requests
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings
from django.shortcuts import get_object_or_404

from ..imports.mercadopago_nacional_sync import link_stored_payment_to_transaction
from ..models import MercadoPagoStoredPayment, Source, Transaction
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


class MercadoPagoLinkSerializer(serializers.Serializer):
    mp_payment_id = serializers.IntegerField(min_value=1)
    transaction_id = serializers.UUIDField()


def _visa_transaction_link_validation_error(visa_tx: Transaction) -> Response | None:
    if visa_tx.source != Source.CREDIT_CARD_NATIONAL:
        return Response(
            {
                "detail": "Only credit card national (Visa Nacional) transactions "
                "can be linked."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if visa_tx.splits.exists():
        return Response(
            {
                "detail": "Cannot link a transaction that has been split into "
                "sub-transactions."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if (visa_tx.currency or "").upper() != "CLP":
        return Response(
            {"detail": "Transaction currency must be CLP."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _payment_dict_from_sdk_raw(
    raw: dict,
    mp_payment_id: int,
) -> dict | Response:
    """Return payment dict or an error :class:`Response`."""

    code, body = _normalize_sdk_payload(raw)
    if code >= 400:
        return Response(body, status=code)
    if not isinstance(body, dict):
        return Response(
            {"detail": "Unexpected Mercado Pago response."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    resp_id = body.get("id")
    if resp_id is not None and int(resp_id) != int(mp_payment_id):
        return Response(
            {"detail": "Mercado Pago response id does not match requested payment."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if (body.get("currency_id") or "").upper() != "CLP":
        return Response(
            {"detail": "Mercado Pago payment must be in CLP."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return body


def _get_clp_payment_body_or_error(
    mp_payment_id: int,
) -> tuple[dict | None, Response | None]:
    try:
        raw = get_payment(str(mp_payment_id))
    except MissingMercadoPagoTokenError as exc:
        return None, Response(
            {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except Exception as exc:  # pylint: disable=broad-except
        return None, Response(
            {"detail": f"Mercado Pago request failed: {exc!s}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    result = _payment_dict_from_sdk_raw(raw, mp_payment_id)
    if isinstance(result, Response):
        return None, result
    return result, None


class MercadoPagoStoredPaymentLinkView(APIView):
    """Link a Mercado Pago payment (by id) to a Visa Nacional transaction."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if not (settings.MERCADOPAGO_ACCESS_TOKEN or "").strip():
            return Response(
                {"detail": "Mercado Pago access token is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        ser = MercadoPagoLinkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        mp_payment_id = ser.validated_data["mp_payment_id"]
        transaction_id = ser.validated_data["transaction_id"]

        visa_tx = get_object_or_404(
            Transaction.objects.filter(user=request.user), pk=transaction_id
        )
        err = _visa_transaction_link_validation_error(visa_tx)
        if err is not None:
            return err

        payment_body, pay_err = _get_clp_payment_body_or_error(mp_payment_id)
        if pay_err is not None:
            return pay_err

        try:
            sp = link_stored_payment_to_transaction(request.user, visa_tx, payment_body)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "stored_payment_id": str(sp.pk),
                "mp_payment_id": sp.mp_payment_id,
                "transaction_id": str(visa_tx.pk),
            }
        )


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


class MercadoPagoStoredPaymentDetailView(APIView):
    """Return stored MP payment JSON (same shape as live payment) for the modal."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        row = get_object_or_404(
            MercadoPagoStoredPayment.objects.filter(user=request.user), pk=pk
        )
        return Response(row.payload)
