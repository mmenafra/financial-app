from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    CategoryViewSet,
    ForgotPasswordView,
    GoogleAuthView,
    HealthCheckView,
    ImportBankStatementView,
    ImportVisaInternationalStatementView,
    ImportVisaNationalStatementView,
    RecurringPatternViewSet,
    ResetPasswordView,
    SignInView,
    SignUpView,
    TransactionViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register(
    "recurring-patterns", RecurringPatternViewSet, basename="recurring-pattern"
)

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("auth/signup/", SignUpView.as_view(), name="signup"),
    path("auth/signin/", SignInView.as_view(), name="signin"),
    path("auth/google/", GoogleAuthView.as_view(), name="google-auth"),
    path("auth/forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("auth/reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path(
        "transactions/import-bank-statement/",
        ImportBankStatementView.as_view(),
        name="import-bank-statement",
    ),
    path(
        "transactions/import-visa-national/",
        ImportVisaNationalStatementView.as_view(),
        name="import-visa-national",
    ),
    path(
        "transactions/import-visa-international/",
        ImportVisaInternationalStatementView.as_view(),
        name="import-visa-international",
    ),
    path("", include(router.urls)),
]
