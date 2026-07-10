# Alignement avec l'app mobile (voir ALIGNEMENT_MOBILE.md · P1)
# Ajoute : assignment_type, broadcast_radius_km, preferred_courier, payment_method
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("couriers", "0003_courier_vehicle_fields"),
        ("services", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicerequest",
            name="assignment_type",
            field=models.CharField(
                choices=[
                    ("broadcast", "Diffusion aux coursiers proches"),
                    ("direct", "Coursier choisi par le client"),
                ],
                default="broadcast",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="servicerequest",
            name="broadcast_radius_km",
            field=models.PositiveSmallIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="servicerequest",
            name="preferred_courier",
            field=models.ForeignKey(
                blank=True,
                help_text="Renseigné uniquement en attribution directe",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="preferred_requests",
                to="couriers.courier",
            ),
        ),
        migrations.AddField(
            model_name="servicerequest",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cash", "Espèces"),
                    ("orange_money", "Orange Money"),
                    ("mtn_momo", "MTN MoMo"),
                    ("wave", "Wave"),
                    ("stripe", "Carte bancaire"),
                ],
                default="cash",
                max_length=20,
            ),
        ),
    ]
