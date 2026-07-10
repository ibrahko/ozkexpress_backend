# E4 : coursiers favoris (voir ALIGNEMENT_MOBILE.md · P5)
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("couriers", "0003_courier_vehicle_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="FavoriteCourier",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorite_couriers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "courier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorited_by",
                        to="couriers.courier",
                    ),
                ),
            ],
            options={
                "verbose_name": "Coursier favori",
                "verbose_name_plural": "Coursiers favoris",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="favoritecourier",
            constraint=models.UniqueConstraint(fields=("client", "courier"), name="unique_client_courier_favorite"),
        ),
    ]
