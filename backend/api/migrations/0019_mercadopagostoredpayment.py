import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api", "0018_transaction_is_hidden"),
    ]

    operations = [
        migrations.CreateModel(
            name="MercadoPagoStoredPayment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("mp_payment_id", models.BigIntegerField(db_index=True)),
                ("synced_at", models.DateTimeField()),
                ("payload", models.JSONField()),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mercadopago_stored_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "visa_transaction",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mercadopago_stored_payment",
                        to="api.transaction",
                    ),
                ),
            ],
            options={
                "ordering": ["-synced_at", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="mercadopagostoredpayment",
            constraint=models.UniqueConstraint(
                fields=("user", "mp_payment_id"),
                name="api_mercadopagostoredpayment_user_mp_id_uniq",
            ),
        ),
    ]
