"""Aggregated spending stats for the Stats UI (monthly breakdown and category trends)."""

import calendar
from datetime import date
from decimal import Decimal
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Q, Sum

from ..models import Category, Direction, Transaction


def _int_param(raw: str | None, default: int, min_v: int, max_v: int) -> int:
    try:
        v = int(raw) if raw is not None and raw != "" else default
    except ValueError:
        return default
    return max(min_v, min(max_v, v))


def _allowed_category_qs(user):
    return Category.objects.filter(Q(user=user) | Q(user__isnull=True))


def _month_keys_starting_at(start_year: int, start_month: int, count: int) -> list[str]:
    keys: list[str] = []
    y, m = start_year, start_month
    for _ in range(count):
        keys.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return keys


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Add delta months (may be negative). Returns (year, month)."""

    idx = year * 12 + (month - 1) + delta
    new_y = idx // 12
    new_m = idx % 12 + 1
    return new_y, new_m


class StatsMonthlyView(APIView):
    """Expense totals per category for one calendar month (pie + table).

    GET /api/stats/monthly/?month=5&year=2026

    Categories with zero total for the month are omitted.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        month = _int_param(request.query_params.get("month"), today.month, 1, 12)
        year = _int_param(request.query_params.get("year"), today.year, 1970, 2100)

        allowed_ids = list(
            _allowed_category_qs(request.user).values_list("id", flat=True)
        )
        if not allowed_ids:
            return Response(
                {
                    "month": month,
                    "year": year,
                    "total": "0.00",
                    "categories": [],
                }
            )

        rows = list(
            Transaction.objects.filter(
                user=request.user,
                direction=Direction.EXPENSE,
                transaction_date__year=year,
                transaction_date__month=month,
                transaction_date__isnull=False,
                category_id__in=allowed_ids,
            )
            .visible_only()
            .values("category_id")
            .annotate(total=Sum("amount"))
            .filter(total__gt=0)
            .order_by("-total")
        )

        cat_ids = [r["category_id"] for r in rows if r["category_id"] is not None]
        cats = {
            str(c.id): c
            for c in Category.objects.filter(id__in=cat_ids).select_related("parent")
        }

        grand = sum((r["total"] or Decimal("0") for r in rows), Decimal("0"))

        categories_data = []
        for row in rows:
            cid = row["category_id"]
            if cid is None:
                continue
            cat = cats.get(str(cid))
            if cat is None:
                continue
            amt: Decimal = row["total"] or Decimal("0")
            if amt <= 0:
                continue
            pct = Decimal("0")
            if grand > 0:
                pct = (amt / grand) * Decimal("100")
            categories_data.append(
                {
                    "id": str(cat.id),
                    "name": cat.name,
                    "icon": cat.icon,
                    "color": cat.color,
                    "amount": str(amt.quantize(Decimal("0.01"))),
                    "percentage": float(pct.quantize(Decimal("0.01"))),
                }
            )

        return Response(
            {
                "month": month,
                "year": year,
                "total": str(grand.quantize(Decimal("0.01"))),
                "categories": categories_data,
            }
        )


class StatsTrendView(APIView):
    """Last 12 months of expense totals for one category (line chart).

    GET /api/stats/category-trend/?category_id=…&reference_month=5&reference_year=2026

    Window ends at reference_month/reference_year (inclusive).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cat_raw = request.query_params.get("category_id", "").strip()
        if not cat_raw:
            return Response(
                {"detail": "category_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cat_uuid = UUID(cat_raw)
        except ValueError:
            return Response(
                {"detail": "category_id must be a valid UUID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = date.today()
        ref_month = _int_param(
            request.query_params.get("reference_month"), today.month, 1, 12
        )
        ref_year = _int_param(
            request.query_params.get("reference_year"), today.year, 1970, 2100
        )

        cat = (
            _allowed_category_qs(request.user)
            .filter(id=cat_uuid)
            .select_related("parent")
            .first()
        )
        if cat is None:
            return Response(
                {"detail": "Category not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        start_year, start_month = _add_months(ref_year, ref_month, -11)
        start_d = date(start_year, start_month, 1)
        end_day = calendar.monthrange(ref_year, ref_month)[1]
        end_d = date(ref_year, ref_month, end_day)

        agg = (
            Transaction.objects.filter(
                user=request.user,
                direction=Direction.EXPENSE,
                category_id=cat_uuid,
                transaction_date__gte=start_d,
                transaction_date__lte=end_d,
                transaction_date__isnull=False,
            )
            .visible_only()
            .values("transaction_date__year", "transaction_date__month")
            .annotate(total=Sum("amount"))
        )
        by_key: dict[str, Decimal] = {}
        for row in agg:
            y, m = row["transaction_date__year"], row["transaction_date__month"]
            if y is None or m is None:
                continue
            key = f"{y}-{int(m):02d}"
            by_key[key] = row["total"] or Decimal("0")

        month_keys = _month_keys_starting_at(start_year, start_month, 12)
        totals = [
            str(by_key.get(k, Decimal("0")).quantize(Decimal("0.01")))
            for k in month_keys
        ]

        return Response(
            {
                "category": {
                    "id": str(cat.id),
                    "name": cat.name,
                    "icon": cat.icon,
                    "color": cat.color,
                },
                "months": month_keys,
                "totals": totals,
            }
        )
