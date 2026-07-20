# P4 : pourboires, zones statistiques, matrice de distances entre quartiers
import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0005_load_bamako_zones"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicerequest",
            name="tip_amount",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10,
                help_text="Pourboire du client (100 % reversé au coursier)",
            ),
        ),
        migrations.AddField(
            model_name="riderequest",
            name="tip_amount",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10,
                help_text="Pourboire du client (100 % reversé au chauffeur)",
            ),
        ),
        migrations.AddField(
            model_name="servicerequest",
            name="pickup_zone",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="pickups_services", to="services.zone",
            ),
        ),
        migrations.AddField(
            model_name="servicerequest",
            name="delivery_zone",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="deliveries_services", to="services.zone",
            ),
        ),
        migrations.AddField(
            model_name="riderequest",
            name="pickup_zone",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="pickups_rides", to="services.zone",
            ),
        ),
        migrations.AddField(
            model_name="riderequest",
            name="dropoff_zone",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="dropoffs_rides", to="services.zone",
            ),
        ),
        migrations.CreateModel(
            name="ZoneDistance",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("road_km", models.DecimalField(decimal_places=2, help_text="Distance routière en km", max_digits=6)),
                (
                    "zone_from",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="distances_from", to="services.zone",
                    ),
                ),
                (
                    "zone_to",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="distances_to", to="services.zone",
                    ),
                ),
            ],
            options={
                "verbose_name": "Distance entre quartiers",
                "verbose_name_plural": "Distances entre quartiers",
            },
        ),
        migrations.AddConstraint(
            model_name="zonedistance",
            constraint=models.UniqueConstraint(fields=("zone_from", "zone_to"), name="unique_zone_pair"),
        ),
    ]
