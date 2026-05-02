from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0017_recurringpattern_unique_normalized_pattern"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="is_hidden",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
