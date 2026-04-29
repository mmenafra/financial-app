import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_visa_international_statement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="visa_international_statement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="transactions",
                to="api.visainternationalstatement",
            ),
        ),
    ]
