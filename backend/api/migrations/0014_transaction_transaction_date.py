# Generated manually for transaction_date rollout

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0013_remove_visa_nacional_period_start"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="transaction_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="transaction",
            options={"ordering": ["-transaction_date", "-created_at"]},
        ),
    ]
