# Generated manually — adds Transaction.matched_recurring_pattern

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0008_split_lines_created_at_from_parent"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="matched_recurring_pattern",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="matched_transactions",
                to="api.recurringpattern",
                db_index=True,
            ),
        ),
    ]
