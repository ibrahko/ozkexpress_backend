"""
Libellés français des champs, appliqués au démarrage (BackofficeConfig.ready).

Beaucoup de champs des modèles n'ont pas de verbose_name : Django affiche alors
leur nom technique (« vehicle type », « phone number »…) dans les colonnes, les
filtres et les formulaires du back-office. Plutôt que de modifier chaque champ,
ce glossaire unique fournit la traduction. Seuls les champs SANS verbose_name
explicite sont concernés : un libellé défini dans un modèle reste prioritaire.
"""

FIELD_LABELS = {
    # Dates et suivi
    "created_at": "créé le", "updated_at": "modifié le", "accepted_at": "acceptée le",
    "picked_up_at": "récupérée le", "delivered_at": "livrée le", "cancelled_at": "annulée le",
    "started_at": "démarrée le", "completed_at": "terminée le", "resolved_at": "résolu le",
    "processed_at": "traitée le", "initiated_at": "initiée le", "failed_at": "échouée le",
    "verified_at": "vérifié le", "read_at": "lu le", "expires_at": "expire le",
    "earned_at": "gagné le", "last_login": "dernière connexion",
    "last_location_update": "position mise à jour le",
    "start_date": "début", "end_date": "fin", "actual_end_date": "fin réelle",
    "insurance_expiry": "fin d'assurance", "vignette_expiry": "fin de vignette",
    "technical_visit_expiry": "fin de visite technique", "registration_expiry": "fin de carte grise",
    "last_maintenance_date": "dernier entretien",

    # Personnes
    "user": "utilisateur", "client": "client", "courier": "coursier", "driver": "chauffeur",
    "preferred_courier": "coursier choisi", "sender": "expéditeur", "recipient": "destinataire",
    "opened_by": "ouvert par", "assigned_to": "attribué à", "verified_by": "vérifié par",
    "worker_user": "travailleur", "first_name": "prénom", "last_name": "nom", "email": "e-mail",
    "phone": "téléphone", "phone_number": "numéro de téléphone", "avatar": "photo de profil",
    "user_type": "rôle", "preferred_language": "langue", "push_token": "jeton de notification",
    "is_phone_verified": "téléphone vérifié", "is_email_verified": "e-mail vérifié",
    "is_staff": "accès au back-office", "is_active": "actif",

    # Statuts et généralités
    "status": "statut", "reason": "motif", "description": "description", "resolution": "résolution",
    "label": "libellé", "name": "nom", "title": "titre", "body": "message", "content": "message",
    "data": "données", "code": "code", "is_used": "utilisé", "is_read": "lu", "sent_push": "push envoyée",
    "notification_type": "type de notification", "attachment": "pièce jointe", "file": "fichier",
    "photo": "photo", "admin_note": "note interne", "admin_notes": "notes internes",
    "client_notes": "notes du client", "is_default": "par défaut",

    # Adresses et géographie
    "address": "adresse", "latitude": "latitude", "longitude": "longitude", "location": "position",
    "center": "centre", "commune": "commune", "zone_from": "quartier de départ", "zone_to": "quartier d'arrivée",
    "road_km": "distance routière (km)",
    "pickup_address": "adresse de départ", "pickup_location": "position de départ",
    "pickup_contact_name": "contact au départ", "pickup_contact_phone": "téléphone au départ",
    "pickup_instructions": "instructions au départ", "pickup_zone": "quartier de départ",
    "delivery_address": "adresse de livraison", "delivery_location": "position de livraison",
    "delivery_contact_name": "contact à l'arrivée", "delivery_contact_phone": "téléphone à l'arrivée",
    "delivery_instructions": "instructions à l'arrivée", "delivery_zone": "quartier d'arrivée",
    "dropoff_address": "adresse d'arrivée", "dropoff_location": "position d'arrivée",
    "dropoff_zone": "quartier d'arrivée", "last_known_location": "dernière position",
    "service_area": "zone d'activité", "delivery_zone_radius_km": "rayon de livraison (km)",
    "broadcast_radius_km": "rayon de diffusion (km)", "speed_kmh": "vitesse (km/h)",
    "heading": "cap", "accuracy_m": "précision (m)",

    # Commandes
    "service_request": "livraison", "ride_request": "course", "fleet_rental": "location",
    "rental": "location", "dispute": "litige", "assignment_type": "attribution",
    "package_description": "description du colis", "package_size": "taille du colis",
    "is_fragile": "fragile", "estimated_weight_kg": "poids estimé (kg)",
    "cancellation_reason": "motif d'annulation", "cancellation_note": "précision sur l'annulation",
    "client_rating": "note du client", "client_review": "avis du client",
    "passenger_count": "passagers", "client_has_own_vehicle": "véhicule du client",
    "special_instructions": "instructions", "duration_minutes": "durée (min)",
    "with_driver": "avec chauffeur",

    # Argent
    "amount": "montant", "currency": "devise", "estimated_price": "prix estimé",
    "final_price": "prix final", "distance_km": "distance (km)", "tip_amount": "pourboire",
    "payment_method": "moyen de paiement", "payment_type": "type de paiement", "provider": "opérateur",
    "reference": "référence", "provider_transaction_id": "référence opérateur",
    "provider_response": "réponse de l'opérateur", "failure_reason": "motif d'échec",
    "wallet": "portefeuille", "balance": "solde", "total_earned": "total gagné",
    "total_withdrawn": "total retiré", "gross_amount": "montant brut", "net_amount": "montant net",
    "commission_rate": "taux de commission (%)", "commission_amount": "commission",
    "refund_amount": "remboursement", "total_price": "prix total", "deposit_amount": "caution",
    "deposit_returned": "caution rendue", "daily_rate": "tarif / jour", "hourly_rate": "tarif / heure",

    # Travailleurs et véhicules
    "vehicle": "véhicule", "vehicle_type": "type de véhicule", "vehicle_category": "catégorie",
    "vehicle_brand": "marque", "vehicle_model": "modèle", "vehicle_year": "année",
    "vehicle_color": "couleur", "vehicle_plate": "plaque", "chassis_number": "numéro de châssis",
    "license_number": "numéro de permis", "brand": "marque", "model": "modèle", "year": "année",
    "color": "couleur", "plate_number": "plaque", "mileage_km": "kilométrage",
    "passenger_capacity": "places passagers", "requires_driver": "chauffeur obligatoire",
    "owns_vehicle": "propriétaire du véhicule", "service_type": "type de service",
    "rating": "note", "total_trips": "courses effectuées", "total_earnings": "gains cumulés",
    "is_available": "disponible", "max_package_size": "taille de colis max.",
    "accepts_fragile": "accepte le fragile", "accepts_documents": "accepte les documents",
    "doc_type": "type de document", "is_verified": "vérifié", "rejection_reason": "motif du refus",
    "content_type": "type de travailleur", "object_id": "identifiant du travailleur",
}


def apply_field_labels():
    from django.apps import apps

    for model in apps.get_models():
        if not model.__module__.startswith("apps."):
            continue
        for field in model._meta.get_fields():
            label = FIELD_LABELS.get(field.name)
            if not label or not hasattr(field, "verbose_name"):
                continue
            # On ne remplace que le libellé auto-généré à partir du nom du champ
            if field.verbose_name == field.name.replace("_", " "):
                field.verbose_name = label
