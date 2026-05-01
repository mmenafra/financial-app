"""Side effects when recurring subscription patterns change."""

from __future__ import annotations

import logging

from django.db.models import Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from ..models import RecurringPattern, Transaction
from .match import (
    q_substring_matches_recurring_haystack,
    refresh_matched_recurring_from_patterns,
)

logger = logging.getLogger(__name__)

# Carries DB state across pre_save → post_save (not model fields).
_PREVIOUS_RECURRING_SNAPSHOT = "_recurring_previous_pattern_snapshot"


@receiver(pre_save, sender=RecurringPattern)
def _recurring_pattern_store_previous_description(
    instance: RecurringPattern,
    **_kwargs,
) -> None:
    prev: tuple[str, str] | None = None
    if RecurringPattern.objects.filter(pk=instance.pk).exists():
        row = RecurringPattern.objects.only("description_pattern", "match_type").get(
            pk=instance.pk
        )
        prev = (row.description_pattern, row.match_type)
    instance.__dict__[_PREVIOUS_RECURRING_SNAPSHOT] = prev


@receiver(post_save, sender=RecurringPattern)
def _recurring_pattern_refresh_matching_transactions(
    instance: RecurringPattern,
    created: bool,
    **_kwargs,
) -> None:
    prev = instance.__dict__.pop(_PREVIOUS_RECURRING_SNAPSHOT, None)
    user = instance.user
    if user is None:
        return
    curr = instance.description_pattern
    if not created and prev is not None:
        prev_pat, prev_mt = prev
        if prev_pat == curr and prev_mt == instance.match_type:
            return

    q = Q(matched_recurring_pattern_id=instance.pk)
    curr_s = (curr or "").strip()
    if curr_s:
        q |= q_substring_matches_recurring_haystack(curr_s)

    prev_s = prev.strip() if isinstance(prev, str) else ""

    if prev_s and (created or prev_s != curr_s):
        q |= q_substring_matches_recurring_haystack(prev_s)

    tx_ids = (
        Transaction.objects.filter(user=user)
        .filter(q)
        .values_list("pk", flat=True)
        .distinct()
    )
    for tx_id in tx_ids:
        try:
            refresh_matched_recurring_from_patterns(user, tx_id)
        except Exception:  # pylint: disable=broad-except  # pragma: no cover - defensive log
            logger.exception(
                "refresh_matched_recurring_from_patterns failed tx_id=%s pattern_id=%s",
                tx_id,
                instance.pk,
            )
