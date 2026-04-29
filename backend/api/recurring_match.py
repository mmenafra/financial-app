"""Match transaction descriptions to user-defined recurring patterns (subscriptions)."""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from .models import RecurringPattern


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
