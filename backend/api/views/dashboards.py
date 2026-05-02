from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..imports.visa_international_statements import (
    select_statement_for_period_end_month,
)
from ..imports.visa_nacional_statements import (
    select_nacional_statement_for_period_end_month,
)
from ..models import (
    Source,
    Transaction,
    VisaInternationalStatement,
    VisaNacionalStatement,
)
from ..serializers import (
    TransactionSerializer,
    VisaInternationalStatementSerializer,
    VisaNacionalStatementSerializer,
)
from .transactions import _query_param_non_empty, _rolling_calendar_months


class VisaInternationalDashboardView(APIView):
    """Statement + transactions + rolling 12-month chart keyed by statement closing month."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="year",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Calendar year used with `month` to pick the statement (by `period_end`).",
            ),
            OpenApiParameter(
                name="month",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Calendar month (1–12) of `period_end` for the statement.",
            ),
        ],
        responses={
            200: inline_serializer(
                name="VisaInternationalDashboardResponse",
                fields={
                    "statement": serializers.JSONField(allow_null=True),
                    "transactions": serializers.ListField(
                        child=serializers.JSONField()
                    ),
                    "monthly_totals": serializers.ListField(
                        child=inline_serializer(
                            name="VisaMonthlyTotal",
                            fields={
                                "year": serializers.IntegerField(),
                                "month": serializers.IntegerField(),
                                "total": serializers.CharField(),
                            },
                        ),
                        help_text=(
                            "Twelve months ending at (year, month): each `total` is "
                            "`VisaInternationalStatement.total_amount` for the user's "
                            "statement whose `period_end` falls in that calendar month, "
                            "else 0."
                        ),
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid or missing year/month"),
        },
    )
    def get(self, request):
        year_raw = request.query_params.get("year")
        month_raw = request.query_params.get("month")
        if not _query_param_non_empty(year_raw) or not _query_param_non_empty(
            month_raw
        ):
            raise ValidationError(
                {"detail": "Both year and month query parameters are required."}
            )
        try:
            year = int(year_raw)
            month = int(month_raw)
        except (TypeError, ValueError) as err:
            raise ValidationError(
                {"year": "Must be valid integers.", "month": "Must be valid integers."}
            ) from err
        if month < 1 or month > 12:
            raise ValidationError({"month": "Must be between 1 and 12."})
        if year < 1 or year > 9999:
            raise ValidationError({"year": "Invalid year."})

        user = request.user
        statement = select_statement_for_period_end_month(user, year, month)

        if statement:
            txs = (
                Transaction.objects.filter(
                    user=user,
                    visa_international_statement=statement,
                    splits__isnull=True,
                )
                .visible_only()
                .order_by("transaction_date", "created_at")
            )
        else:
            # Legacy / pre-parent rows: no statement with this closing month — show calendar month.
            txs = (
                Transaction.objects.filter(
                    user=user,
                    source=Source.CREDIT_CARD_INTERNATIONAL,
                    splits__isnull=True,
                    transaction_date__year=year,
                    transaction_date__month=month,
                )
                .visible_only()
                .order_by("transaction_date", "created_at")
            )

        months = _rolling_calendar_months(year, month, 12)
        stmt_by_period: dict[tuple[int, int], VisaInternationalStatement | None] = {}
        for y, m in months:
            stmt_by_period[(y, m)] = select_statement_for_period_end_month(user, y, m)

        monthly_totals = []
        for y, m in months:
            stmt_m = stmt_by_period.get((y, m))
            total = stmt_m.total_amount if stmt_m else Decimal("0")
            monthly_totals.append({"year": y, "month": m, "total": str(total)})

        stmt_payload = (
            VisaInternationalStatementSerializer(
                statement, context={"request": request}
            ).data
            if statement
            else None
        )
        tx_payload = TransactionSerializer(
            txs, many=True, context={"request": request}
        ).data
        return Response(
            {
                "statement": stmt_payload,
                "transactions": tx_payload,
                "monthly_totals": monthly_totals,
            }
        )


class VisaNacionalDashboardView(APIView):
    """Statement + transactions + rolling 12-month chart keyed by statement closing month (CLP)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="year",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Calendar year used with `month` to pick the statement (by `period_end`).",
            ),
            OpenApiParameter(
                name="month",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Calendar month (1–12) of `period_end` for the statement.",
            ),
        ],
        responses={
            200: inline_serializer(
                name="VisaNacionalDashboardResponse",
                fields={
                    "statement": serializers.JSONField(allow_null=True),
                    "transactions": serializers.ListField(
                        child=serializers.JSONField()
                    ),
                    "monthly_totals": serializers.ListField(
                        child=inline_serializer(
                            name="VisaNacionalMonthlyTotal",
                            fields={
                                "year": serializers.IntegerField(),
                                "month": serializers.IntegerField(),
                                "total": serializers.CharField(),
                            },
                        ),
                        help_text=(
                            "Twelve months ending at (year, month): each `total` is "
                            "`VisaNacionalStatement.total_amount` for the user's "
                            "statement whose `period_end` falls in that calendar month, "
                            "else 0."
                        ),
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid or missing year/month"),
        },
    )
    def get(self, request):
        year_raw = request.query_params.get("year")
        month_raw = request.query_params.get("month")
        if not _query_param_non_empty(year_raw) or not _query_param_non_empty(
            month_raw
        ):
            raise ValidationError(
                {"detail": "Both year and month query parameters are required."}
            )
        try:
            year = int(year_raw)
            month = int(month_raw)
        except (TypeError, ValueError) as err:
            raise ValidationError(
                {"year": "Must be valid integers.", "month": "Must be valid integers."}
            ) from err
        if month < 1 or month > 12:
            raise ValidationError({"month": "Must be between 1 and 12."})
        if year < 1 or year > 9999:
            raise ValidationError({"year": "Invalid year."})

        user = request.user
        statement = select_nacional_statement_for_period_end_month(user, year, month)

        if statement:
            txs = (
                Transaction.objects.filter(
                    user=user,
                    visa_nacional_statement=statement,
                    splits__isnull=True,
                )
                .visible_only()
                .order_by("transaction_date", "created_at")
            )
        else:
            txs = (
                Transaction.objects.filter(
                    user=user,
                    source=Source.CREDIT_CARD_NATIONAL,
                    splits__isnull=True,
                    transaction_date__year=year,
                    transaction_date__month=month,
                )
                .visible_only()
                .order_by("transaction_date", "created_at")
            )

        months = _rolling_calendar_months(year, month, 12)
        stmt_by_period: dict[tuple[int, int], VisaNacionalStatement | None] = {}
        for y, m in months:
            stmt_by_period[(y, m)] = select_nacional_statement_for_period_end_month(
                user, y, m
            )

        monthly_totals = []
        for y, m in months:
            stmt_m = stmt_by_period.get((y, m))
            total = stmt_m.total_amount if stmt_m else Decimal("0")
            monthly_totals.append({"year": y, "month": m, "total": str(total)})

        stmt_payload = (
            VisaNacionalStatementSerializer(
                statement, context={"request": request}
            ).data
            if statement
            else None
        )
        tx_payload = TransactionSerializer(
            txs, many=True, context={"request": request}
        ).data
        return Response(
            {
                "statement": stmt_payload,
                "transactions": tx_payload,
                "monthly_totals": monthly_totals,
            }
        )
