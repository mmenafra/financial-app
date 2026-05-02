import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Q, Sum

from ..models import Category, Transaction

logger = logging.getLogger(__name__)


class HistoricView(APIView):
    """Monthly spending breakdown per category for a given calendar year.

    GET /api/historic/?categories=id1,id2&year=2025

    Query params:
        categories  Comma-separated category UUIDs (required, at least one).
        year        Calendar year to show (default: current year).

    Response:
        {
          "year": 2025,
          "months": ["2025-01", ..., "2025-12"],
          "categories": [
            {
              "id": "...",
              "name": "...",
              "icon": "...",
              "color": "...",
              "monthly_totals": {"2025-01": "150.00", ...}
            }
          ]
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw_ids = request.query_params.get("categories", "")
        category_ids = [c.strip() for c in raw_ids.split(",") if c.strip()]
        if not category_ids:
            return Response({"year": date.today().year, "months": [], "categories": []})

        today = date.today()
        try:
            year = int(request.query_params.get("year", today.year))
        except ValueError:
            year = today.year

        months = [f"{year}-{m:02d}" for m in range(1, 13)]

        categories = list(
            Category.objects.filter(
                Q(user=request.user) | Q(user__isnull=True),
                id__in=category_ids,
            ).order_by("name")
        )

        existing_ids = {str(c.id) for c in categories}
        requested_ids = [i for i in category_ids if i in existing_ids]

        if not categories:
            return Response({"year": year, "months": months, "categories": []})

        qs = (
            Transaction.objects.filter(
                user=request.user,
                direction="EXPENSE",
                category__in=[str(c.id) for c in categories],
                transaction_date__year=year,
                transaction_date__isnull=False,
            )
            .visible_only()
            .values("category", "transaction_date__month")
            .annotate(total=Sum("amount"))
        )

        totals: dict[str, dict[str, Decimal]] = defaultdict(dict)
        for row in qs:
            month_key = f"{year}-{row['transaction_date__month']:02d}"
            cat_id = str(row["category"])
            totals[cat_id][month_key] = row["total"] or Decimal("0")

        cat_map = {str(c.id): c for c in categories}
        categories_data = []
        for cat_id in requested_ids:
            if cat_id not in cat_map:
                continue
            cat = cat_map[cat_id]
            monthly = totals.get(cat_id, {})
            categories_data.append(
                {
                    "id": str(cat.id),
                    "name": cat.name,
                    "icon": cat.icon,
                    "color": cat.color,
                    "monthly_totals": {
                        m: str(monthly.get(m, Decimal("0"))) for m in months
                    },
                }
            )

        return Response({"year": year, "months": months, "categories": categories_data})
