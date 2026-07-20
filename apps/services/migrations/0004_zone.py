# Quartiers de Bamako pour la tarification par distance (200 F/km)
import uuid
import django.contrib.gis.db.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0003_message"),
    ]

    operations = [
        migrations.CreateModel(
            name="Zone",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("commune", models.CharField(blank=True, max_length=50)),
                ("center", django.contrib.gis.db.models.fields.PointField(srid=4326)),
            ],
            options={
                "verbose_name": "Quartier",
                "verbose_name_plural": "Quartiers",
                "ordering": ["name"],
            },
        ),
    ]
