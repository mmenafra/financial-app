from django.contrib import admin

from .models import Category, RecurringPattern, Transaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "parent", "icon", "color", "created_at")
    search_fields = ("name",)
    list_filter = ("created_at",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "description",
        "user",
        "amount",
        "currency",
        "source",
        "direction",
        "status",
        "created_at",
    )
    search_fields = ("description", "external_id", "original_reference")
    list_filter = ("source", "direction", "status", "is_installment", "created_at")


@admin.register(RecurringPattern)
class RecurringPatternAdmin(admin.ModelAdmin):
    list_display = ("description_pattern", "user", "category", "frequency", "expected_amount")
    search_fields = ("description_pattern",)
    list_filter = ("frequency", "created_at")
