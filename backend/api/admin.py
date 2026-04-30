from django.contrib import admin

from .models import Category, FileImport, RecurringPattern, Transaction


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
        "transaction_date",
        "created_at",
    )
    search_fields = ("description", "external_id", "original_reference")
    list_filter = (
        "source",
        "direction",
        "status",
        "is_installment",
        "transaction_date",
        "created_at",
    )


@admin.register(FileImport)
class FileImportAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "user",
        "source",
        "status",
        "rows_imported",
        "rows_skipped",
        "created_at",
    )
    list_filter = ("source", "status", "created_at")
    search_fields = ("original_filename",)


@admin.register(RecurringPattern)
class RecurringPatternAdmin(admin.ModelAdmin):
    list_display = (
        "description_pattern",
        "user",
        "frequency",
        "expected_amount",
    )
    search_fields = ("description_pattern",)
    list_filter = ("frequency", "created_at")
