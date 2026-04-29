# Remove VisaNacionalStatement.period_start (cierre = period_end from PDF only)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_visa_nacional_statement"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="visanacionalstatement",
            name="period_start",
        ),
    ]
