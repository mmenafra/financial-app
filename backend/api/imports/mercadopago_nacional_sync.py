"""Sync Mercado Pago payments and link Visa Nacional CLP rows (import pipeline)."""

from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime, time
from datetime import timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..mercadopago.client import MissingMercadoPagoTokenError
from ..mercadopago.search import search_payments_all_in_range
from ..models import (
    Direction,
    MercadoPagoStoredPayment,
    Source,
    Transaction,
    VisaNacionalStatement,
)

logger = logging.getLogger(__name__)


def _debug_json(obj: Any, max_len: int = 100_000) -> str:
    """Serialize ``obj`` for DEBUG logs; truncate very large payloads."""

    try:
        s = json.dumps(obj, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        s = repr(obj)
    if len(s) > max_len:
        return f"{s[:max_len]}... [truncated, total_len={len(s)}]"
    return s


def _payment_debug_snapshot(payment: dict[str, Any]) -> dict[str, Any]:
    """Compact shape for logs (avoids dumping full MP payloads unless needed)."""

    td = payment.get("transaction_details")
    td = td if isinstance(td, dict) else {}
    desc = payment.get("description")
    return {
        "id": payment.get("id"),
        "status": payment.get("status"),
        "currency_id": payment.get("currency_id"),
        "date_created": payment.get("date_created"),
        "date_approved": payment.get("date_approved"),
        "transaction_amount": payment.get("transaction_amount"),
        "total_paid_amount": td.get("total_paid_amount"),
        "description": (str(desc)[:200] if desc else None),
    }


def _transaction_debug_snapshot(tx: Transaction) -> dict[str, Any]:
    return {
        "id": str(tx.pk),
        "transaction_date": (
            tx.transaction_date.isoformat() if tx.transaction_date else None
        ),
        "amount": str(tx.amount),
        "description": (tx.description[:200] if tx.description else None),
    }


def add_calendar_months(d: date, delta_months: int) -> date:
    """Add calendar months to ``d``, clamping the day to the target month's length."""

    m = d.month - 1 + delta_months
    y = d.year + m // 12
    m = m % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    day = min(d.day, last_day)
    return date(y, m, day)


def mercadopago_search_window_iso_utc(period_end: date) -> tuple[str, str]:
    """MP search window: start of (period_end - 2 months) through end of period_end (UTC).

    Uses ``…T00:00:00.000Z`` / ``…T23:59:59.000Z`` — high-resolution ``time.max``
    microseconds are rejected by the Payments Search API in practice.
    """

    begin = add_calendar_months(period_end, -2)
    start_dt = datetime.combine(begin, time(0, 0, 0), tzinfo=dt_timezone.utc)
    end_dt = datetime.combine(period_end, time(23, 59, 59), tzinfo=dt_timezone.utc)

    def _mp_iso_z(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"

    return _mp_iso_z(start_dt), _mp_iso_z(end_dt)


def mp_total_amount(payment: dict[str, Any]) -> Decimal | None:
    """Total paid for matching (prefer ``transaction_details.total_paid_amount``)."""

    td = payment.get("transaction_details")
    if isinstance(td, dict):
        raw = td.get("total_paid_amount")
        if raw is not None:
            try:
                return Decimal(str(raw))
            except (InvalidOperation, ValueError, TypeError):
                pass
    raw = payment.get("transaction_amount")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _payment_calendar_date(payment: dict[str, Any]) -> date | None:
    for key in ("date_approved", "date_created"):
        raw = payment.get(key)
        if not raw or not isinstance(raw, str):
            continue
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                continue
    return None


def _amounts_equal_clp(a: Decimal, b: Decimal, tol: Decimal = Decimal("1")) -> bool:
    return abs(a - b) <= tol


def visa_description_is_mp_like(description: str) -> bool:
    """Heuristic: Visa PDF text suggests Mercado Pago / MercadoLibre."""

    if not description:
        return False
    normalized = " ".join(description.strip().upper().split())
    tokens = (
        "MERCADOPAGO",
        "MERCADO PAGO",
        "MERCADOLIBRE",
        "MERCADO LIBRE",
        "MELI",
        "M PAGO",
    )
    return any(t in normalized for t in tokens)


def mp_display_title(payment: dict[str, Any]) -> str | None:
    items = payment.get("additional_info")
    if isinstance(items, dict):
        raw_items = items.get("items")
        if isinstance(raw_items, list) and raw_items:
            first = raw_items[0]
            if isinstance(first, dict):
                title = first.get("title")
                if title:
                    return str(title)[:255]
    for key in ("description", "statement_descriptor"):
        v = payment.get(key)
        if v:
            return str(v)[:255]
    return None


def _upsert_stored_payments_for_rows(
    user,
    mp_rows: list[dict],
    now,
) -> dict[int, MercadoPagoStoredPayment]:
    stored_by_mp_id: dict[int, MercadoPagoStoredPayment] = {}
    for row in mp_rows:
        pid = row.get("id")
        if pid is None:
            continue
        try:
            mp_id = int(pid)
        except (TypeError, ValueError):
            continue
        obj, _created = MercadoPagoStoredPayment.objects.update_or_create(
            user=user,
            mp_payment_id=mp_id,
            defaults={
                "payload": row,
                "synced_at": now,
            },
        )
        stored_by_mp_id[mp_id] = obj
    return stored_by_mp_id


def _matching_edges(
    candidate_txs: list[Transaction],
    stored_by_mp_id: dict[int, MercadoPagoStoredPayment],
) -> list[tuple[Transaction, MercadoPagoStoredPayment]]:
    edges: list[tuple[Transaction, MercadoPagoStoredPayment]] = []
    for tx in candidate_txs:
        vamt = tx.amount
        vdate = tx.transaction_date
        if vdate is None:
            continue
        for _mp_id, sp in stored_by_mp_id.items():
            pay = sp.payload if isinstance(sp.payload, dict) else {}
            if (pay.get("currency_id") or "").upper() != "CLP":
                continue
            total = mp_total_amount(pay)
            if total is None:
                continue
            pdate = _payment_calendar_date(pay)
            if pdate is None:
                continue
            if abs((pdate - vdate).days) > 2:
                continue
            if not _amounts_equal_clp(vamt, total):
                continue
            edges.append((tx, sp))
    return edges


def _mutually_unique_pairs(
    edges: list[tuple[Transaction, MercadoPagoStoredPayment]],
) -> list[tuple[Transaction, MercadoPagoStoredPayment]]:
    by_tx: dict[Any, list[MercadoPagoStoredPayment]] = {}
    by_sp: dict[int, list[Any]] = {}
    for tx, sp in edges:
        by_tx.setdefault(tx.pk, []).append(sp)
        by_sp.setdefault(sp.mp_payment_id, []).append(tx)

    final_pairs: list[tuple[Transaction, MercadoPagoStoredPayment]] = []
    for tx, sp in edges:
        if len(by_tx[tx.pk]) != 1:
            continue
        if len(by_sp[sp.mp_payment_id]) != 1:
            continue
        if by_tx[tx.pk][0].mp_payment_id != sp.mp_payment_id:
            continue
        if by_sp[sp.mp_payment_id][0].pk != tx.pk:
            continue
        final_pairs.append((tx, sp))
    return final_pairs


def _link_summary_for_sync(
    user,
    candidate_txs: list[Transaction],
    final_pairs: list[tuple[Transaction, MercadoPagoStoredPayment]],
) -> tuple[int, list[dict[str, Any]]]:
    summary: list[dict[str, Any]] = []
    links = 0
    for tx, sp in final_pairs:
        MercadoPagoStoredPayment.objects.filter(
            user=user, visa_transaction_id=tx.pk
        ).exclude(pk=sp.pk).update(visa_transaction=None)
        sp.visa_transaction_id = tx.pk
        sp.save(update_fields=["visa_transaction", "updated_at"])
        pay = sp.payload if isinstance(sp.payload, dict) else {}
        title = mp_display_title(pay)
        if title:
            Transaction.objects.filter(pk=tx.pk).update(
                description=title,
                external_name=title,
                updated_at=timezone.now(),
            )
        links += 1
        tot = mp_total_amount(pay)
        summary.append(
            {
                "transaction_id": str(tx.pk),
                "mp_payment_id": sp.mp_payment_id,
                "mp_total_amount": str(tot) if tot is not None else None,
                "visa_amount": str(tx.amount),
                "linked": True,
                "display_title": title,
            }
        )

    linked_tx_ids = {str(t.pk) for t, _ in final_pairs}
    for tx in candidate_txs:
        tid = str(tx.pk)
        if tid in linked_tx_ids:
            continue
        summary.append(
            {
                "transaction_id": tid,
                "mp_payment_id": None,
                "mp_total_amount": None,
                "visa_amount": str(tx.amount),
                "linked": False,
                "display_title": None,
            }
        )
    return links, summary


def link_stored_payment_to_transaction(
    user,
    visa_transaction: Transaction,
    payment_payload: dict[str, Any],
) -> MercadoPagoStoredPayment:
    """Upsert stored payment from ``payment_payload`` and attach ``visa_transaction``.

    Clears any other stored payment rows for this user that pointed at the same Visa tx.
    When :func:`mp_display_title` returns a title, updates the transaction ``description``
    and ``external_name`` (same behaviour as import sync).
    """

    pid = payment_payload.get("id")
    if pid is None:
        msg = "payment payload missing id"
        raise ValueError(msg)
    try:
        mp_id = int(pid)
    except (TypeError, ValueError) as exc:
        msg = "invalid mp payment id"
        raise ValueError(msg) from exc

    now = timezone.now()
    with transaction.atomic():
        sp, _created = MercadoPagoStoredPayment.objects.update_or_create(
            user=user,
            mp_payment_id=mp_id,
            defaults={
                "payload": payment_payload,
                "synced_at": now,
            },
        )
        MercadoPagoStoredPayment.objects.filter(
            user=user, visa_transaction_id=visa_transaction.pk
        ).exclude(pk=sp.pk).update(visa_transaction=None)
        sp.visa_transaction_id = visa_transaction.pk
        sp.save(update_fields=["visa_transaction", "updated_at"])

        title = mp_display_title(payment_payload)
        if title:
            Transaction.objects.filter(pk=visa_transaction.pk).update(
                description=title,
                external_name=title,
                updated_at=timezone.now(),
            )
    return sp


def sync_and_link_visa_nacional_statement(
    user,
    visa_statement: VisaNacionalStatement,
    period_end: date,
) -> dict[str, Any]:
    """Fetch MP payments in range, upsert snapshots, link matching Nacional txs.

    Updates each linked :class:`Transaction` ``description`` and ``external_name``
    to the Mercado Pago display title when one can be derived from the payment payload
    (item title, ``description``, or ``statement_descriptor``).
    """

    empty = {
        "mercadopago_payments_synced": 0,
        "mercadopago_links_created": 0,
        "mercadopago_sync_skipped_no_token": False,
        "mercadopago_sync_error": None,
        "mercadopago_link_summary": [],
    }
    if not (settings.MERCADOPAGO_ACCESS_TOKEN or "").strip():
        empty["mercadopago_sync_skipped_no_token"] = True
        return empty

    begin_iso, end_iso = mercadopago_search_window_iso_utc(period_end)
    logger.debug(
        "Visa Nacional Mercado Pago sync: statement_id=%s period_end=%s "
        "search_window_utc=[%s, %s] range_field=date_created",
        getattr(visa_statement, "pk", None),
        period_end,
        begin_iso,
        end_iso,
    )
    try:
        mp_rows = search_payments_all_in_range(
            begin_date=begin_iso,
            end_date=end_iso,
            range_field="date_created",
        )
    except MissingMercadoPagoTokenError as exc:
        return {
            **empty,
            "mercadopago_sync_error": str(exc),
        }
    except RuntimeError as exc:
        # Expected when MP returns 4xx/5xx on /v1/payments/search (details in message).
        logger.warning("Mercado Pago payments search failed: %s", exc)
        return {
            **empty,
            "mercadopago_sync_error": str(exc),
        }
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Mercado Pago nacional sync failed")
        return {
            **empty,
            "mercadopago_sync_error": str(exc),
        }

    now = timezone.now()

    qs_txs = list(
        Transaction.objects.filter(
            user=user,
            visa_nacional_statement=visa_statement,
            source=Source.CREDIT_CARD_NATIONAL,
            direction=Direction.EXPENSE,
        )
    )
    logger.debug(
        "Visa Nacional Mercado Pago sync: user_id=%s nacional_expense_rows=%s "
        "(before MP-description filter)",
        getattr(user, "pk", None),
        len(qs_txs),
    )
    logger.debug(
        "Visa Nacional Mercado Pago sync: pre_filter_transactions=%s",
        _debug_json([_transaction_debug_snapshot(t) for t in qs_txs]),
    )

    candidate_txs = [t for t in qs_txs if visa_description_is_mp_like(t.description)]
    logger.debug(
        "Visa Nacional Mercado Pago sync: mp_like_candidate_transactions count=%s "
        "snapshots=%s",
        len(candidate_txs),
        _debug_json([_transaction_debug_snapshot(t) for t in candidate_txs]),
    )

    logger.debug(
        "Visa Nacional Mercado Pago sync: mp_rows count=%s payment_snapshots=%s",
        len(mp_rows),
        _debug_json(
            [_payment_debug_snapshot(r) for r in mp_rows if isinstance(r, dict)]
        ),
    )
    logger.debug(
        "Visa Nacional Mercado Pago sync: full mp_rows list=%s",
        _debug_json(mp_rows),
    )

    with transaction.atomic():
        MercadoPagoStoredPayment.objects.filter(
            user=user,
            visa_transaction__in=[t.pk for t in candidate_txs],
        ).update(visa_transaction=None)

        stored_by_mp_id = _upsert_stored_payments_for_rows(user, mp_rows, now)
        edges = _matching_edges(candidate_txs, stored_by_mp_id)
        final_pairs = _mutually_unique_pairs(edges)
        logger.debug(
            "Visa Nacional Mercado Pago sync: stored_payments=%s matching_edges=%s "
            "mutually_unique_pairs=%s",
            len(stored_by_mp_id),
            len(edges),
            len(final_pairs),
        )
        logger.debug(
            "Visa Nacional Mercado Pago sync: edge pairs (tx_id, mp_payment_id)=%s",
            _debug_json([(str(tx.pk), sp.mp_payment_id) for tx, sp in edges]),
        )
        logger.debug(
            "Visa Nacional Mercado Pago sync: final link pairs (tx_id, mp_payment_id)=%s",
            _debug_json([(str(tx.pk), sp.mp_payment_id) for tx, sp in final_pairs]),
        )
        links, summary = _link_summary_for_sync(user, candidate_txs, final_pairs)

    return {
        "mercadopago_payments_synced": len(mp_rows),
        "mercadopago_links_created": links,
        "mercadopago_sync_skipped_no_token": False,
        "mercadopago_sync_error": None,
        "mercadopago_link_summary": summary,
    }
