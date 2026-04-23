from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    ForgotPasswordView,
    HealthCheckView,
    RecurringPatternViewSet,
    ResetPasswordView,
    SignInView,
    SignUpView,
    TransactionViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("recurring-patterns", RecurringPatternViewSet, basename="recurring-pattern")

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("auth/signup/", SignUpView.as_view(), name="signup"),
    path("auth/signin/", SignInView.as_view(), name="signin"),
    path("auth/forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("auth/reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path("", include(router.urls)),
]
