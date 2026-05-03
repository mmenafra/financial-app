"""Helpers for Mercado Pago payment search pagination and response parsing."""

from __future__ import annotations

import json
import logging
from typing import Any

from .client import search_payments

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


def payment_search_extract(raw: dict) -> tuple[int, list[dict], dict]:
    """Return (http_status, results, paging) from an SDK ``payment().search`` result."""

    status_code = int(raw.get("status", 200))
    response_body = raw.get("response")
    if isinstance(response_body, dict):
        results = response_body.get("results") or []
        if not isinstance(results, list):
            results = []
        paging = response_body.get("paging") or {}
        if not isinstance(paging, dict):
            paging = {}
        return status_code, results, paging
    if isinstance(response_body, list):
        return status_code, response_body, {}
    return status_code, [], {}


def _format_search_http_error(raw: dict) -> str:
    """Human-readable message from SDK ``{"status": int, "response": ...}``."""

    status = raw.get("status", "?")
    body = raw.get("response")
    if isinstance(body, dict):
        msg = body.get("message")
        err = body.get("error")
        cause = body.get("cause")
        if isinstance(cause, list) and cause:
            cause = cause[0] if isinstance(cause[0], str) else str(cause[0])
        if msg:
            return f"Mercado Pago search HTTP {status}: {msg}"
        if err and cause:
            return f"Mercado Pago search HTTP {status}: {err} — {cause}"
        if err:
            return f"Mercado Pago search HTTP {status}: {err}"
        return f"Mercado Pago search HTTP {status}: {body}"
    if body is not None:
        return f"Mercado Pago search HTTP {status}: {body!r}"
    return f"Mercado Pago search HTTP {status} (empty body)"


def search_payments_all_in_range(
    *,
    begin_date: str,
    end_date: str,
    range_field: str = "date_created",
    max_offset: int = 10_000,
) -> list[dict]:
    """Fetch all payments in ``[begin_date, end_date]`` for ``range_field``, paginating.

    Raises ``RuntimeError`` if Mercado Pago returns a non-success HTTP status.
    """

    all_results: list[dict] = []
    offset = 0
    limit = 50
    total: int | None = None

    while offset <= max_offset:
        raw = search_payments(
            offset=offset,
            limit=limit,
            begin_date=begin_date,
            end_date=end_date,
            range_field=range_field,
        )
        response_body = raw.get("response")
        logger.debug(
            "Mercado Pago payments search page offset=%s limit=%s begin=%s end=%s "
            "range_field=%s http_status=%s response_body=%s",
            offset,
            limit,
            begin_date,
            end_date,
            range_field,
            raw.get("status"),
            _debug_json(response_body),
        )
        status, chunk, paging = payment_search_extract(raw)
        if status >= 400:
            raise RuntimeError(_format_search_http_error(raw))
        all_results.extend(chunk)
        if paging.get("total") is not None:
            total = int(paging["total"])
        offset += len(chunk)
        if not chunk:
            break
        if total is not None and offset >= total:
            break

    return all_results
