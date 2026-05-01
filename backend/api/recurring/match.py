"""Match transactions to user-defined recurring patterns (subscriptions)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractUser
from django.db.models import Q

from ..models import RecurringPattern, Transaction


def recurring_match_haystack(
    external_name: str | None,
    description: str | None,
) -> str:
    """
    Stable text used for substring matching against ``RecurringPattern.description_pattern``.

    Prefer non-empty ``external_name`` (set at import / create, not updated when the user
    edits ``description``). Fall back to ``description`` for legacy rows without
    ``external_name``.
    """
    ext = (external_name or "").strip()
    if ext:
        return ext
    return (description or "").strip()


def q_substring_matches_recurring_haystack(substring: str) -> Q:
    """
    ``Q`` for transactions where ``substring`` matches the same haystack rule as
    :func:`recurring_match_haystack` (non-empty ``external_name`` only, else ``description``).
    """
    s = (substring or "").strip()
    if not s:
        return Q(pk__in=[])
    has_stable = Q(external_name__isnull=False) & ~Q(external_name="")
    stable_match = has_stable & Q(external_name__icontains=s)
    legacy = Q(external_name__isnull=True) | Q(external_name="")
    legacy_match = legacy & Q(description__icontains=s)
    return stable_match | legacy_match


def match_recurring_pattern_for_description(
    user: AbstractUser,
    text: str,
) -> RecurringPattern | None:
    """
    Return the best matching RecurringPattern for this user, or None.

    ``text`` is typically :func:`recurring_match_haystack` for a transaction.

    Rule: case-insensitive substring match (`pattern in text`).
    Tie-break: longest `description_pattern` wins; then smallest pk for stability.
    """
    if not text or not text.strip():
        return None

    desc_lower = text.lower()
    patterns = list(
        RecurringPattern.objects.filter(user=user).only(
            "id",
            "description_pattern",
        ),
    )
    matches: list[RecurringPattern] = []
    for pat in patterns:
        needle = (pat.description_pattern or "").strip().lower()
        if needle and needle in desc_lower:
            matches.append(pat)
    if not matches:
        return None

    def sort_key(p: RecurringPattern) -> tuple[int, str]:
        return (-len(p.description_pattern), str(p.pk))

    return sorted(matches, key=sort_key)[0]


def apply_recurring_match_if_missing(user: AbstractUser, transaction_id: Any) -> None:
    """
    If ``matched_recurring_pattern`` is unset, set it when a pattern matches the haystack.

    Used for Visa import (new rows and skipped duplicate rows) so re-imports
    backfill after users add patterns, without overwriting an explicit future override.
    """
    if not Transaction.objects.filter(
        pk=transaction_id,
        matched_recurring_pattern__isnull=True,
    ).exists():
        return
    tx = (
        Transaction.objects.filter(pk=transaction_id)
        .only("pk", "description", "external_name")
        .first()
    )
    if tx is None:
        return
    hay = recurring_match_haystack(tx.external_name, tx.description)
    best = match_recurring_pattern_for_description(user, hay)
    if best is None:
        return
    Transaction.objects.filter(
        pk=transaction_id,
        matched_recurring_pattern__isnull=True,
    ).update(matched_recurring_pattern=best)


def refresh_matched_recurring_from_patterns(
    user: AbstractUser, transaction_id: Any
) -> None:
    """
    Recompute ``matched_recurring_pattern`` from all of the user's patterns (or clear it).

    Used when recurring patterns are created/edited so existing transactions stay consistent.
    """
    tx = (
        Transaction.objects.filter(pk=transaction_id)
        .only("pk", "description", "external_name")
        .first()
    )
    if tx is None:
        return
    hay = recurring_match_haystack(tx.external_name, tx.description)
    best = match_recurring_pattern_for_description(user, hay)
    Transaction.objects.filter(pk=tx.pk).update(
        matched_recurring_pattern=best if best is not None else None,
    )
