# Chargement des quartiers de Bamako (coordonnées indicatives, à affiner sur le terrain)
from django.db import migrations

# (nom, commune, lat, lng)
BAMAKO_ZONES = [
    # Commune I
    ("Djélibougou", "Commune I", 12.6740, -7.9770),
    ("Boulkassoumbougou", "Commune I", 12.6850, -7.9550),
    ("Korofina", "Commune I", 12.6720, -7.9660),
    ("Banconi", "Commune I", 12.6900, -7.9650),
    ("Sotuba", "Commune I", 12.6600, -7.9300),
    # Commune II
    ("Zone Industrielle", "Commune II", 12.6350, -7.9720),
    ("Hippodrome", "Commune II", 12.6530, -7.9800),
    ("Médina Coura", "Commune II", 12.6520, -7.9890),
    ("Niaréla", "Commune II", 12.6450, -7.9830),
    ("Bagadadji", "Commune II", 12.6500, -7.9850),
    ("Quinzambougou", "Commune II", 12.6480, -7.9780),
    # Commune III
    ("Bamako Coura", "Commune III", 12.6450, -7.9950),
    ("Badialan", "Commune III", 12.6480, -8.0050),
    ("Centre Commercial", "Commune III", 12.6490, -7.9930),
    ("Point G", "Commune III", 12.6680, -7.9970),
    # Commune IV
    ("ACI 2000", "Commune IV", 12.6390, -8.0140),
    ("Hamdallaye", "Commune IV", 12.6430, -8.0200),
    ("Lafiabougou", "Commune IV", 12.6400, -8.0300),
    ("Djicoroni Para", "Commune IV", 12.6250, -8.0330),
    ("Sébénikoro", "Commune IV", 12.6180, -8.0550),
    # Commune V
    ("Badalabougou", "Commune V", 12.6240, -7.9860),
    ("Quartier Mali", "Commune V", 12.6150, -7.9900),
    ("Torokorobougou", "Commune V", 12.6180, -7.9970),
    ("Baco Djicoroni", "Commune V", 12.6050, -8.0050),
    ("Sabalibougou", "Commune V", 12.6100, -7.9850),
    ("Kalaban Coura", "Commune V", 12.5950, -7.9800),
    # Commune VI
    ("Magnambougou", "Commune VI", 12.6100, -7.9490),
    ("Sogoniko", "Commune VI", 12.6150, -7.9550),
    ("Faladié", "Commune VI", 12.6000, -7.9450),
    ("Niamakoro", "Commune VI", 12.5950, -7.9550),
    ("Yirimadio", "Commune VI", 12.6050, -7.9150),
    ("Banankabougou", "Commune VI", 12.6000, -7.9300),
    ("Missabougou", "Commune VI", 12.6300, -7.9200),
]


def load_zones(apps, schema_editor):
    from django.contrib.gis.geos import Point
    Zone = apps.get_model("services", "Zone")
    for name, commune, lat, lng in BAMAKO_ZONES:
        Zone.objects.update_or_create(
            name=name,
            defaults={"commune": commune, "center": Point(lng, lat, srid=4326)},
        )


def unload_zones(apps, schema_editor):
    Zone = apps.get_model("services", "Zone")
    Zone.objects.filter(name__in=[z[0] for z in BAMAKO_ZONES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0004_zone"),
    ]

    operations = [
        migrations.RunPython(load_zones, unload_zones),
    ]
