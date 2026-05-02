from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from ..models import Category, Direction, Source, Transaction
from ..pagination import TransactionPagination
from ..serializers import (
    CategorySerializer,
    TransactionSerializer,
    TransactionSplitRequestSerializer,
)

_SOURCE_QUERY_ENUM = [choice.value for choice in Source]


def _query_param_non_empty(raw) -> bool:
    return raw is not None and str(raw).strip() != ""


def _query_param_truthy(raw) -> bool:
    if raw is None:
        return False
    normalized = str(raw).strip().lower()
    return normalized in frozenset({"1", "true", "yes", "on"})


def _rolling_calendar_months(
    end_year: int, end_month: int, n: int = 12
) -> list[tuple[int, int]]:
    """Return oldest-first list of (year, month) tuples, ending at (end_year, end_month)."""
    months: list[tuple[int, int]] = []
    y, m = end_year, end_month
    for _ in range(n):
        months.append((y, m))
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1
    months.reverse()
    return months


def _apply_transaction_year_filter(qs, year_raw):
    if not _query_param_non_empty(year_raw):
        return qs
    try:
        year = int(year_raw)
    except (TypeError, ValueError) as err:
        raise ValidationError({"year": "Must be a valid integer."}) from err
    if year < 1 or year > 9999:
        raise ValidationError({"year": "Invalid year."})
    return qs.filter(transaction_date__year=year)


def _apply_transaction_month_filter(qs, month_raw):
    if not _query_param_non_empty(month_raw):
        return qs
    try:
        month = int(month_raw)
    except (TypeError, ValueError) as err:
        raise ValidationError({"month": "Must be a valid integer."}) from err
    if month < 1 or month > 12:
        raise ValidationError({"month": "Must be between 1 and 12."})
    return qs.filter(transaction_date__month=month)


def _apply_transaction_category_filter(qs, category_id, user):
    if not _query_param_non_empty(category_id):
        return qs
    if not Category.objects.filter(pk=category_id, user=user).exists():
        raise ValidationError(
            {"category": "Category must belong to the authenticated user."}
        )
    return qs.filter(category_id=category_id)


def _apply_transaction_source_filter(qs, source_raw):
    if not _query_param_non_empty(source_raw):
        return qs
    if source_raw not in _SOURCE_QUERY_ENUM:
        raise ValidationError(
            {
                "source": (
                    f"Invalid source. Must be one of: {', '.join(_SOURCE_QUERY_ENUM)}."
                )
            }
        )
    return qs.filter(source=source_raw)


def _expense_total_amount_str(value) -> str:
    """Two-decimal string for API totals (SQLite Sum can yield int for whole amounts)."""
    d = Decimal("0") if value is None else Decimal(str(value))
    return format(d.quantize(Decimal("0.01")), "f")


def _expense_totals_by_currency(queryset):
    """Sum EXPENSE amounts per ISO currency code for queryset (pre-filtered).

    Uses the same queryset as the list/table (before pagination).
    Returns ``{currency: amount_str}, ...``.
    """
    rows = (
        queryset.filter(direction="EXPENSE")
        .values("currency")
        .annotate(total=Sum("amount"))
        .order_by("currency")
    )
    return {row["currency"]: _expense_total_amount_str(row["total"]) for row in rows}


def _filter_transactions_list_queryset(qs, query_params, user):
    """Apply optional GET /transactions/ filters. Raises ValidationError if invalid."""
    year_raw = query_params.get("year")
    month_raw = query_params.get("month")
    if _query_param_non_empty(month_raw) and not _query_param_non_empty(year_raw):
        raise ValidationError({"month": "year is required when month is provided."})
    qs = _apply_transaction_year_filter(qs, year_raw)
    qs = _apply_transaction_month_filter(qs, month_raw)
    qs = _apply_transaction_category_filter(qs, query_params.get("category"), user)
    qs = _apply_transaction_source_filter(qs, query_params.get("source"))
    return qs


def _filter_income_list_queryset(qs, query_params):
    """Apply optional GET /income/ filters: year, month, source only (no category)."""
    year_raw = query_params.get("year")
    month_raw = query_params.get("month")
    if _query_param_non_empty(month_raw) and not _query_param_non_empty(year_raw):
        raise ValidationError({"month": "year is required when month is provided."})
    qs = _apply_transaction_year_filter(qs, year_raw)
    qs = _apply_transaction_month_filter(qs, month_raw)
    qs = _apply_transaction_source_filter(qs, query_params.get("source"))
    return qs


def _income_monthly_totals(request, user):
    """Twelve calendar months of income totals for the chart."""
    year_raw = request.query_params.get("year")
    month_raw = request.query_params.get("month")
    if _query_param_non_empty(year_raw) and _query_param_non_empty(month_raw):
        end_year, end_month = int(year_raw), int(month_raw)
    elif _query_param_non_empty(year_raw):
        end_year = int(year_raw)
        end_month = 12
    else:
        today = timezone.now().date()
        end_year, end_month = today.year, today.month
    months = _rolling_calendar_months(end_year, end_month, 12)
    base = Transaction.objects.filter(
        user=user, direction=Direction.INCOME, splits__isnull=True
    ).visible_only()
    base = _apply_transaction_source_filter(base, request.query_params.get("source"))
    monthly_totals = []
    for y, m in months:
        total = base.filter(
            transaction_date__year=y, transaction_date__month=m
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        monthly_totals.append({"year": y, "month": m, "total": str(total)})
    return monthly_totals


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="year",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
            description=(
                "Filter by calendar year of `transaction_date`. "
                "Use together with `month` to restrict to a single month."
            ),
            examples=[OpenApiExample("Current year", value=2026)],
        ),
        OpenApiParameter(
            name="month",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
            description=(
                "Filter by calendar month (1–12) of `transaction_date`. "
                "Requires `year` to be set."
            ),
            examples=[OpenApiExample("April", value=4)],
        ),
        OpenApiParameter(
            name="source",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Filter by transaction source.",
            enum=_SOURCE_QUERY_ENUM,
            examples=[OpenApiExample("Mercado Pago", value=Source.MERCADOPAGO.value)],
        ),
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Page number (1-based).",
            examples=[OpenApiExample("First page", value=1)],
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
            description=(
                "Number of results per page. Capped at the API maximum (e.g. 100)."
            ),
            examples=[OpenApiExample("Default size", value=100)],
        ),
    ],
)
class IncomeView(ListAPIView):
    """Paginated INCOME transactions with rolling 12-month totals."""

    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TransactionPagination

    def get_queryset(self):
        qs = Transaction.objects.filter(
            user=self.request.user,
            direction=Direction.INCOME,
            splits__isnull=True,
        ).visible_only()
        return _filter_income_list_queryset(qs, self.request.query_params)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        monthly_totals = _income_monthly_totals(request, request.user)

        page = self.paginate_queryset(queryset)
        extra = {"monthly_totals": monthly_totals}
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data.update(extra)
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({"results": serializer.data, **extra})


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="year",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Filter by calendar year of `transaction_date`. "
                    "Use together with `month` to restrict to a single month."
                ),
                examples=[OpenApiExample("Current year", value=2026)],
            ),
            OpenApiParameter(
                name="month",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Filter by calendar month (1–12) of `transaction_date`. "
                    "Requires `year` to be set."
                ),
                examples=[OpenApiExample("April", value=4)],
            ),
            OpenApiParameter(
                name="category",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by category id (must be one of your categories).",
            ),
            OpenApiParameter(
                name="source",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by transaction source.",
                enum=_SOURCE_QUERY_ENUM,
                examples=[
                    OpenApiExample("Mercado Pago", value=Source.MERCADOPAGO.value)
                ],
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Page number (1-based).",
                examples=[OpenApiExample("First page", value=1)],
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Number of results per page. Capped at the API maximum (e.g. 100)."
                ),
                examples=[OpenApiExample("Default size", value=100)],
            ),
            OpenApiParameter(
                name="include_hidden",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Include transactions hidden from aggregates and other screens; "
                    "when false or omitted only visible rows appear (default)."
                ),
            ),
        ],
    ),
)
class TransactionViewSet(ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TransactionPagination

    def get_queryset(self):
        qs = Transaction.objects.filter(user=self.request.user)
        if self.action != "list":
            return qs
        qs = qs.filter(splits__isnull=True)
        qs = _filter_transactions_list_queryset(
            qs, self.request.query_params, self.request.user
        )
        if not _query_param_truthy(self.request.query_params.get("include_hidden")):
            qs = qs.visible_only()
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Aggregate total expenses for the current filter period (legacy single field).
        total_spent = queryset.filter(direction="EXPENSE").aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")
        totals_by_currency = _expense_totals_by_currency(queryset)

        # Aggregate expenses for the previous calendar month (same category/source).
        year_raw = request.query_params.get("year")
        month_raw = request.query_params.get("month")
        prev_spent = Decimal("0")
        prev_totals_by_currency = {}
        if _query_param_non_empty(year_raw) and _query_param_non_empty(month_raw):
            year = int(year_raw)
            month = int(month_raw)
            prev_year = year - 1 if month == 1 else year
            prev_month = 12 if month == 1 else month - 1
            prev_qs = Transaction.objects.filter(
                user=request.user, splits__isnull=True
            ).filter(
                transaction_date__year=prev_year, transaction_date__month=prev_month
            )
            if not _query_param_truthy(request.query_params.get("include_hidden")):
                prev_qs = prev_qs.visible_only()
            prev_qs = _apply_transaction_category_filter(
                prev_qs, request.query_params.get("category"), request.user
            )
            prev_qs = _apply_transaction_source_filter(
                prev_qs, request.query_params.get("source")
            )
            prev_spent = prev_qs.filter(direction="EXPENSE").aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0")
            prev_totals_by_currency = _expense_totals_by_currency(prev_qs)

        page = self.paginate_queryset(queryset)
        extra = {
            "total_spent": str(total_spent),
            "prev_month_spent": str(prev_spent),
            "totals_by_currency": totals_by_currency,
            "prev_totals_by_currency": prev_totals_by_currency,
        }
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data.update(extra)
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({"results": serializer.data, **extra})

    @extend_schema(
        request=TransactionSplitRequestSerializer,
        responses={201: TransactionSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="split")
    @db_transaction.atomic
    def split(self, request, pk=None):  # pylint: disable=unused-argument
        """Split a top-level transaction into multiple lines (strict amount match)."""
        bundle = self.get_object()
        if bundle.parent_id is not None:
            raise ValidationError(
                {"detail": "Cannot split a transaction that is already a split line."}
            )
        if bundle.splits.exists():
            raise ValidationError({"detail": "This transaction is already split."})

        ser = TransactionSplitRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        items = ser.validated_data["items"]
        if len(items) < 2:
            raise ValidationError({"items": "At least two split lines are required."})

        total = sum((row["amount"] for row in items), Decimal("0"))
        if total != bundle.amount:
            raise ValidationError(
                {"items": "Sum of split amounts must equal the transaction amount."}
            )

        created = []
        for row in items:
            cat_id = row.get("category")
            category = None
            if cat_id is not None:
                try:
                    category = Category.objects.get(pk=cat_id, user=request.user)
                except Category.DoesNotExist as err:
                    raise ValidationError(
                        {
                            "items": "Each category must belong to the authenticated user."
                        }
                    ) from err

            child = Transaction(
                user=bundle.user,
                description=row["description"],
                amount=row["amount"],
                currency=bundle.currency,
                amount_local=None,
                exchange_rate=bundle.exchange_rate,
                transaction_type=bundle.transaction_type,
                direction=bundle.direction,
                category=category,
                subcategory=None,
                source=bundle.source,
                original_reference=bundle.original_reference,
                external_id=None,
                is_installment=False,
                installment_current=None,
                installment_total=None,
                installment_amount=None,
                installment_group_id=None,
                raw_data=None,
                imported_at=bundle.imported_at,
                transaction_date=bundle.transaction_date,
                status=bundle.status,
                parent=bundle,
                file_import=bundle.file_import,
                is_hidden=bundle.is_hidden,
            )
            child.save()
            created.append(child)

        out = TransactionSerializer(created, many=True, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CategoryViewSet(ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
