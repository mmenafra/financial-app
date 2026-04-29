"""Match transaction descriptions to user-defined recurring patterns (subscriptions)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractUser

from .models import RecurringPattern, Transaction


def match_recurring_pattern_for_description(
    user: AbstractUser,
    description: str,
) -> RecurringPattern | None:
    """
    Return the best matching RecurringPattern for this user, or None.

    Rule: case-insensitive substring match (`pattern in description`).
    Tie-break: longest `description_pattern` wins; then smallest pk for stability.
    """
    if not description or not description.strip():
        return None

    desc_lower = description.lower()
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
    If ``matched_recurring_pattern`` is unset, set it when a pattern matches the description.

    Used for Visa International import (new rows and skipped duplicate rows) so re-imports
    backfill after users add patterns, without overwriting an explicit future override.
    """
    if not Transaction.objects.filter(
        pk=transaction_id,
        matched_recurring_pattern__isnull=True,
    ).exists():
        return
    tx = Transaction.objects.filter(pk=transaction_id).only("pk", "description").first()
    if tx is None:
        return
    best = match_recurring_pattern_for_description(user, tx.description or "")
    if best is None:
        return
    Transaction.objects.filter(
        pk=transaction_id,
        matched_recurring_pattern__isnull=True,
    ).update(matched_recurring_pattern=best)


def refresh_matched_recurring_from_patterns(user: AbstractUser, transaction_id: Any) -> None:
    """
    Recompute ``matched_recurring_pattern`` from all of the user's patterns (or clear it).

    Used when recurring patterns are created/edited so existing transactions stay consistent.
    """
    tx = (
        Transaction.objects.filter(pk=transaction_id)
        .only("pk", "description")
        .first()
    )
    if tx is None:
        return
    best = match_recurring_pattern_for_description(user, tx.description or "")
    Transaction.objects.filter(pk=tx.pk).update(
        matched_recurring_pattern=best if best is not None else None,
    )
