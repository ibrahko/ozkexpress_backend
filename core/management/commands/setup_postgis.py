"""
Commande Django pour activer l'extension PostGIS sur la base de données.
À appeler avant les migrations sur Railway (ou tout serveur PostgreSQL).
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Active l'extension PostGIS sur la base de données PostgreSQL."

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology;")
            self.stdout.write(self.style.SUCCESS("PostGIS activé avec succès."))
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"PostGIS : {e} (peut être déjà activé ou non disponible)")
            )
