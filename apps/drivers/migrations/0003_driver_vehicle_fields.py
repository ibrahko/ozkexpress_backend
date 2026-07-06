# Migration manuelle — ajout des champs véhicule complets sur Driver
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("drivers", "0002_initial"),
    ]

    operations = [
        # Type de véhicule
        migrations.AddField(
            model_name="driver",
            name="vehicle_type",
            field=models.CharField(
                choices=[
                    ("moto", "Moto-taxi"),
                    ("tricycle", "Tricycle (Katakatani)"),
                    ("car", "Voiture"),
                    ("van", "Van / Fourgonnette"),
                ],
                default="moto",
                db_index=True,
                max_length=20,
            ),
        ),
        # Marque du véhicule
        migrations.AddField(
            model_name="driver",
            name="vehicle_brand",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Marque (ex: Yamaha, Honda, Bajaj)",
                max_length=100,
            ),
            preserve_default=False,
        ),
        # Numéro de châssis (sachis)
        migrations.AddField(
            model_name="driver",
            name="chassis_number",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Numéro de châssis (numéro sachis)",
                max_length=50,
            ),
            preserve_default=False,
        ),
        # Rendre chassis_number unique après le backfill
        migrations.AlterField(
            model_name="driver",
            name="chassis_number",
            field=models.CharField(
                unique=True,
                help_text="Numéro de châssis (numéro sachis)",
                max_length=50,
            ),
        ),
        # Assurance
        migrations.AddField(
            model_name="driver",
            name="insurance_expiry",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Date d'expiration de l'assurance",
            ),
        ),
        # Vignette
        migrations.AddField(
            model_name="driver",
            name="vignette_expiry",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Date d'expiration de la vignette",
            ),
        ),
        # Visite technique
        migrations.AddField(
            model_name="driver",
            name="technical_visit_expiry",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Date d'expiration de la visite technique",
            ),
        ),
    ]
