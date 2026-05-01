"""Bulk-assign categories to imported transactions using Gemini structured JSON."""

from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from typing import Any
from uuid import UUID

import jsonschema
import requests

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import transaction

from .models import Category, Transaction

logger = logging.getLogger(__name__)


def _gemini_http_enabled() -> bool:
    return bool(getattr(settings, "GEMINI_HTTP_ENABLED", False))


def _gemini_log_prompts_enabled() -> bool:
    """Full prompt logging for live requests when DEBUG or GEMINI_LOG_PROMPTS=1."""
    flag = getattr(settings, "GEMINI_LOG_PROMPTS", None)
    if flag is not None:
        return bool(flag)
    return bool(settings.DEBUG)


def _log_gemini_prompt(
    label: str,
    *,
    user_id: int | None,
    chunk_index: int,
    total_chunks: int,
    transaction_count: int,
    user_message_text: str,
) -> None:
    logger.info(
        "%s: user_id=%s model=%s chunk=%s/%s txs=%s\n"
        "--- system_instruction ---\n%s\n--- user_message ---\n%s",
        label,
        user_id,
        GEMINI_MODEL,
        chunk_index + 1,
        total_chunks,
        transaction_count,
        SYSTEM_PROMPT,
        user_message_text,
    )


GEMINI_MODEL = "gemini-2.5-flash-lite"

GENERATE_CONTENT_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
    ":generateContent"
)

SYSTEM_PROMPT = """You classify merchant or bank-description lines from an imported batch \
onto this user's existing categories. The taxonomy is finite and user-defined — there are \
no free-form labels elsewhere.

Output rules:
- Return only JSON matching the requested schema — no preamble, markdown, or extra keys.
- Completeness: every transaction id listed in the JSON input must appear exactly once \
in your assignments array.
- category_id must equal exactly one id from the input categories array, or be JSON null.
- Do not invent category names, labels, or UUIDs. Never output plausible-looking IDs that \
were not literally present under categories.
- When no category clearly fits or confidence is insufficient, use category_id: null \
(human review).
- Prefer null over guessing. If two plausible categories tie, use null.
- Categories may include parent_id: prefer the most specific (typically leaf) row when \
semantics fit; use a broader parent id only when no descendant fits distinctly better.
- Use direction (INCOME/EXPENSE), transaction_type, and amount to avoid obvious mismatches.
- Descriptions may be multilingual; category name strings define meaning — match semantics \
without inventing taxonomy.

If you cannot determine a matching category from the given categories — none applies, \
ambiguity remains, or the text is meaningless — set category_id to null and do not invent \
identifiers."""

USER_JSON_PRELUDE = (
    "Respond with JSON matching the requested schema using only categories[].id for "
    "category references; classify each transactions[].id once.\n\n"
)


# Gemini REST Schema uses OpenAPI-ish types per API reference (STRING, OBJECT, ARRAY, ...)
GEMINI_ASSIGNMENTS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "assignments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "transaction_id": {"type": "STRING"},
                    "category_id": {
                        "type": "STRING",
                        "nullable": True,
                    },
                },
                "required": ["transaction_id", "category_id"],
            },
        },
    },
    "required": ["assignments"],
}

ASSIGNMENTS_JSONSCHEMA = {
    "type": "object",
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string"},
                    "category_id": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "null"},
                        ],
                    },
                },
                "required": ["transaction_id", "category_id"],
            },
        },
    },
    "required": ["assignments"],
}

CHUNK_SIZE = 50
REQUEST_TIMEOUT = 120
MAX_RETRIES = 2


def _normalize_amount(amount: Decimal) -> str:
    return format(amount, "f")


def serialize_categories_for_gemini(user) -> list[dict[str, Any]]:
    cats = list(Category.objects.filter(user=user))
    cats.sort(key=lambda c: (c.name.lower(), str(c.id)))
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "parent_id": str(c.parent_id) if c.parent_id else None,
        }
        for c in cats
    ]


def serialize_transactions_slice(txs: list[Transaction]) -> list[dict[str, Any]]:
    rows = []
    for tx in txs:
        rows.append(
            {
                "id": str(tx.id),
                "description": tx.description,
                "amount": _normalize_amount(tx.amount),
                "currency": tx.currency,
                "direction": tx.direction,
                "transaction_type": tx.transaction_type,
                "original_reference": tx.original_reference,
            },
        )
    return rows


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in model response")
    return json.loads(text[start : end + 1])


def _extract_text_from_candidate(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts") or []
    texts = []
    for part in parts:
        if isinstance(part.get("text"), str):
            texts.append(part["text"])
    return "\n".join(texts)


def _call_gemini_raw(
    api_key: str,
    body: dict[str, Any],
    *,
    user_id: int | None,
    chunk_index: int,
    total_chunks: int,
    transaction_count: int,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        logger.info(
            "Gemini generateContent start user_id=%s model=%s chunk=%s/%s "
            "transactions_in_chunk=%s attempt=%s/%s",
            user_id,
            GEMINI_MODEL,
            chunk_index + 1,
            total_chunks,
            transaction_count,
            attempt + 1,
            MAX_RETRIES,
        )
        t0 = time.perf_counter()
        try:
            # Uncomment the following line to temporarily disable outbound HTTP regardless of
            # GEMINI_HTTP_ENABLED (remember to revert before deploying).
            # raise RuntimeError("Gemini HTTP short-circuit for local debugging")
            resp = requests.post(
                GENERATE_CONTENT_URL,
                params={"key": api_key.strip()},
                json=body,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            last_exc = exc
            logger.warning(
                "Gemini generateContent network error user_id=%s chunk=%s/%s "
                "attempt=%s/%s elapsed_ms=%s err=%s",
                user_id,
                chunk_index + 1,
                total_chunks,
                attempt + 1,
                MAX_RETRIES,
                elapsed_ms,
                exc,
            )
            if attempt + 1 < MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"Gemini network error: {exc}") from exc

        try:
            payload = resp.json()
        except ValueError:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                "Gemini non-JSON HTTP body user_id=%s chunk=%s/%s "
                "status=%s elapsed_ms=%s",
                user_id,
                chunk_index + 1,
                total_chunks,
                resp.status_code,
                elapsed_ms,
            )
            raise RuntimeError("Gemini returned non-JSON HTTP body") from None

        if resp.status_code in (429,) or resp.status_code >= 500:
            msg = payload.get("error", {}).get("message", "") or resp.text[:200]
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "Gemini generateContent transient HTTP user_id=%s chunk=%s/%s "
                "status=%s attempt=%s/%s elapsed_ms=%s detail=%s",
                user_id,
                chunk_index + 1,
                total_chunks,
                resp.status_code,
                attempt + 1,
                MAX_RETRIES,
                elapsed_ms,
                msg[:300],
            )
            last_exc = RuntimeError(f"{resp.status_code}: {msg}")
            if attempt + 1 < MAX_RETRIES:
                time.sleep(2.0 * (attempt + 1))
                continue

        if resp.status_code >= 400:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            msg = payload.get("error", {}).get("message") or resp.text[:500]
            logger.error(
                "Gemini generateContent HTTP error user_id=%s chunk=%s/%s "
                "status=%s elapsed_ms=%s detail=%s",
                user_id,
                chunk_index + 1,
                total_chunks,
                resp.status_code,
                elapsed_ms,
                msg[:400],
            )
            raise RuntimeError(f"Gemini API error ({resp.status_code}): {msg}")

        text = _extract_text_from_candidate(payload)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "Gemini generateContent ok user_id=%s chunk=%s/%s status=%s "
            "elapsed_ms=%s response_text_len=%s",
            user_id,
            chunk_index + 1,
            total_chunks,
            resp.status_code,
            elapsed_ms,
            len(text),
        )
        return _parse_json_object(text)

    raise RuntimeError(str(last_exc) if last_exc else "Gemini request failed")


def categorize_chunk(
    api_key: str,
    categories_json: list[dict],
    txs: list[Transaction],
    allowed_category_ids: set[str],
    *,
    chunk_index: int = 0,
    total_chunks: int = 1,
    user_id: int | None = None,
) -> dict[UUID, str | None]:
    blob = {
        "categories": categories_json,
        "transactions": serialize_transactions_slice(txs),
    }
    uid = user_id if user_id is not None else (txs[0].user_id if txs else None)
    user_message_text = USER_JSON_PRELUDE + json.dumps(blob, ensure_ascii=False)

    if not _gemini_http_enabled():
        logger.warning(
            "Gemini generateContent skipped (GEMINI_HTTP_ENABLED=False) user_id=%s "
            "chunk=%s/%s transaction_count=%s — no AI categories applied for this chunk",
            uid,
            chunk_index + 1,
            total_chunks,
            len(txs),
        )
        _log_gemini_prompt(
            "Gemini dry-run prompt (would be sent)",
            user_id=uid,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            transaction_count=len(txs),
            user_message_text=user_message_text,
        )
        return {t.pk: None for t in txs}

    if _gemini_log_prompts_enabled():
        _log_gemini_prompt(
            "Gemini prompt",
            user_id=uid,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            transaction_count=len(txs),
            user_message_text=user_message_text,
        )

    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "parts": [
                    {
                        "text": user_message_text,
                    },
                ],
            },
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": GEMINI_ASSIGNMENTS_SCHEMA,
        },
    }
    parsed = _call_gemini_raw(
        api_key,
        body,
        user_id=uid,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        transaction_count=len(txs),
    )

    jsonschema.Draft202012Validator(ASSIGNMENTS_JSONSCHEMA).validate(parsed)

    expected_ids = {str(t.pk) for t in txs}
    assignments = parsed.get("assignments") or []
    decoded: dict[UUID, str | None] = {}
    seen: set[str] = set()

    for item in assignments:
        tid_raw = item.get("transaction_id")
        cat_raw = item.get("category_id")
        try:
            tid = UUID(str(tid_raw))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid transaction_id: {tid_raw!r}") from exc
        sid = str(tid)
        if sid not in expected_ids:
            raise ValueError(f"Unexpected transaction_id in response: {sid}")
        if sid in seen:
            raise ValueError(f"Duplicate transaction_id: {sid}")
        seen.add(sid)

        if cat_raw is None:
            decoded[tid] = None
            continue

        try:
            cat_uuid = UUID(str(cat_raw))
        except (ValueError, TypeError):
            decoded[tid] = None
            continue

        cid_str = str(cat_uuid)
        decoded[tid] = cid_str if cid_str in allowed_category_ids else None

    if seen != expected_ids:
        missing = sorted(expected_ids - seen)
        raise ValueError(f"Missing assignments for transaction ids: {missing}")

    return decoded


def apply_decoded_mappings(user: AbstractUser, mappings: dict[UUID, str | None]) -> int:
    if not mappings:
        return 0

    pk_list = list(mappings.keys())
    pk_to_cat: dict[UUID, Category | None] = {}
    for pk, cid_str in mappings.items():
        pk_to_cat[pk] = None
        if cid_str:
            pk_to_cat[pk] = Category.objects.filter(pk=cid_str, user=user).first()

    with transaction.atomic():
        txs = list(
            Transaction.objects.select_for_update().filter(
                pk__in=pk_list,
                user=user,
            ),
        )
        if len(txs) != len(set(pk_list)):
            raise ValueError("Transaction mismatch for Gemini bulk update")

        updates: list[Transaction] = []
        for tx in txs:
            next_cat = pk_to_cat.get(tx.pk)
            tx.category = next_cat
            updates.append(tx)

        Transaction.objects.bulk_update(updates, ["category"])
    return len(updates)


def run_bulk_categorization(
    user: AbstractUser,
    pending: list[Transaction],
    api_key: str,
):
    """Run Gemini categorization for uncategorized imports.

    On failure returns applied=False without DB updates beyond what already persisted.
    """
    out: dict[str, Any] = {
        "applied": False,
        "updated_count": 0,
        "failure_detail": None,
        "attempted": False,
    }

    if not pending or not (api_key and api_key.strip()):
        return out

    categories_json = serialize_categories_for_gemini(user)
    if not categories_json:
        return out

    allowed_category_ids = {c["id"] for c in categories_json}
    out["attempted"] = True

    n_chunks = (len(pending) + CHUNK_SIZE - 1) // CHUNK_SIZE
    logger.info(
        "Gemini bulk categorization scheduling user_id=%s pending_transactions=%s "
        "categories=%s chunks=%s chunk_size=%s",
        user.pk,
        len(pending),
        len(categories_json),
        n_chunks,
        CHUNK_SIZE,
    )

    merged: dict[UUID, str | None] = {}
    try:
        for ci, start in enumerate(range(0, len(pending), CHUNK_SIZE)):
            chunk = pending[start : start + CHUNK_SIZE]
            merged.update(
                categorize_chunk(
                    api_key,
                    categories_json,
                    chunk,
                    allowed_category_ids,
                    chunk_index=ci,
                    total_chunks=n_chunks,
                    user_id=user.pk,
                )
            )

        count = apply_decoded_mappings(user, merged)
        out["applied"] = True
        out["updated_count"] = count
        logger.info(
            "Gemini bulk categorization succeeded user_id=%s rows_bulk_updated=%s "
            "assignments=%s",
            user.pk,
            count,
            len(merged),
        )
        return out

    except (
        ValueError,
        jsonschema.ValidationError,
        json.JSONDecodeError,
        RuntimeError,
    ) as exc:
        logger.warning(
            "Gemini bulk categorization failed user_id=%s err=%s",
            user.pk,
            exc,
        )
        out["failure_detail"] = str(exc)[:400]
        out["applied"] = False
        return out
