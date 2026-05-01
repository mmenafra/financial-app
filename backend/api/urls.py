from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from django.urls import include, path

from .views import (
    CategoryViewSet,
    FileImportViewSet,
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
    SubscriptionListView,
    TransactionViewSet,
    UserProfileView,
    VisaInternationalDashboardView,
    VisaNacionalDashboardView,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register(
    "recurring-patterns", RecurringPatternViewSet, basename="recurring-pattern"
)
router.register("file-imports", FileImportViewSet, basename="file-import")

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("auth/signup/", SignUpView.as_view(), name="signup"),
    path("auth/signin/", SignInView.as_view(), name="signin"),
    path("auth/google/", GoogleAuthView.as_view(), name="google-auth"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("auth/reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path("auth/profile/", UserProfileView.as_view(), name="user-profile"),
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
    path(
        "visa-international/dashboard/",
        VisaInternationalDashboardView.as_view(),
        name="visa-international-dashboard",
    ),
    path(
        "visa-nacional/dashboard/",
        VisaNacionalDashboardView.as_view(),
        name="visa-nacional-dashboard",
    ),
    path(
        "subscriptions/",
        SubscriptionListView.as_view(),
        name="subscription-list",
    ),
    path("", include(router.urls)),
]
