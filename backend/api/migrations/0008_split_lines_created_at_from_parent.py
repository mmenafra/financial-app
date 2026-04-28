# Backfill split lines so year/month list filters match the parent bundle.

from django.db import migrations
from django.db.models import OuterRef, Subquery


def forwards(apps, schema_editor):
    Transaction = apps.get_model("api", "Transaction")
    parent_created = Transaction.objects.filter(pk=OuterRef("parent_id")).values(
        "created_at"
    )[:1]
    Transaction.objects.filter(parent_id__isnull=False).update(
        created_at=Subquery(parent_created)
    )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_userprofile"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
