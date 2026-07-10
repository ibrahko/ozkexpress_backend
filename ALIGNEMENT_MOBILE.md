# Checklist backend — alignement avec l'app mobile MotoExpress

> Générée le 10/07/2026 après audit croisé `MotoExpressApp` (Expo/RN) ↔ backend Django.
> Le mobile envoie déjà tous les champs listés ci-dessous : chaque case cochée côté backend
> débloque immédiatement une fonctionnalité déjà codée côté app.

---

## 🔴 Priorité 1 — Flux d'envoi de colis (bloquant pour les écrans C2/C3/D1/H2/I2/I5)

### 1. Accepter et persister les champs envoyés à `POST /api/v1/services/`
Le mobile envoie : `assignment_type` (`broadcast` | `direct`), `broadcast_radius_km`,
`payment_method` (`cash` | `orange_money` | `mtn_momo` | `wave` | `stripe`),
`preferred_courier`, `estimated_price`, `distance_km`. Aujourd'hui tout sauf
`distance_km` est ignoré silencieusement par le serializer.

- [x] `apps/services/models.py` · `ServiceRequest` : champs ajoutés ✅ (10/07/2026)
  - [x] `payment_method` (choices `PaymentMethod`)
  - [x] `assignment_type` (choices `AssignmentType`)
  - [x] `broadcast_radius_km` (défaut 5)
  - [x] `preferred_courier` (FK `couriers.Courier`)
- [x] `apps/services/serializers.py` : les 4 champs exposés + `validate()` (direct ⇒ coursier requis)
- [x] Migration écrite : `apps/services/migrations/0002_assignment_payment_fields.py`
      → **à appliquer : `python manage.py migrate services`**

### 2. Calculer `estimated_price` côté serveur (source de vérité)
Formule actuellement utilisée par le mobile (`DELIVERY_PRICING` dans
`src/utils/constants.ts`) : **1 000 FCFA (prise en charge) + 200 FCFA/km + 220 FCFA (frais de service)**.

- [x] `apps/services/pricing.py` créé ✅ (constantes surchargables :
      `DELIVERY_BASE_FARE`, `DELIVERY_PER_KM`, `DELIVERY_SERVICE_FEE`)
- [x] `ServiceRequestSerializer.create()` calcule `distance_km` (haversine) et
      `estimated_price` côté serveur ; les deux sont désormais en lecture seule
- [x] La réponse de création renvoie les valeurs calculées

### 3. Faire respecter la diffusion dans `GET /api/v1/services/available/`
Aujourd'hui la vue renvoie **toutes** les demandes `pending` à **tous** les coursiers.

- [x] Filtrage par distance (annotation PostGIS `Distance` + rayon par demande) ✅
- [x] `direct` : visible et acceptable uniquement par le `preferred_courier`
      (contrôle aussi dans `accept()`) ✅
- [x] Escalade automatique ✅ : dans `available()`, après 60 s le rayon passe à 10 km min,
      après 180 s la demande est visible par tous les coursiers en ligne
      (constantes `ESCALATION_*` dans `apps/services/views.py`)

---

## 🔴 Priorité 2 — Infos coursier dans les réponses ServiceRequest (bloquant pour E1/F1/H2)

Le mobile lit `courier_location` (carte de suivi F1 !), `courier_rating`,
`courier_phone` (bouton Appeler E1), `courier_vehicle`. Le serializer ne renvoie
aujourd'hui que `courier` (id) et `courier_name`.

- [x] `ServiceRequestSerializer` : `courier_location`, `courier_rating`, `courier_phone`,
      `courier_vehicle` ajoutés ✅ (les plaques placeholder « TMP-… » sont masquées)
- [x] `RideRequestSerializer` : `driver_location`, `driver_rating`, `driver_phone`,
      `driver_vehicle` ajoutés ✅

---

## 🔴 Priorité 3 — Profil coursier créé par OTP (bloquant pour toute l'app coursier)

Le mobile authentifie tous les rôles par OTP avec `user_type`. Or `IsCourier` accède à
`request.user.courier_profile`, qui n'existe pas pour un utilisateur `courier` créé via
`VerifyOTPView` → **500 sur tous les endpoints coursier**.

Choisir l'une des deux options :

- [x] **Option A retenue** ✅ : `AuthService._ensure_worker_profile()` crée le profil
      `Courier`/`Driver` (statut `pending`) à la vérification OTP. Les champs uniques
      obligatoires (`vehicle_plate`, `chassis_number`, `license_number`) reçoivent des
      placeholders `TMP-…` à remplacer via `PATCH /couriers/me/`
- [ ] Option B (inscription complète avec documents) : reste possible plus tard via
      `POST /auth/register/courier/` + écrans mobiles dédiés
- [x] Garde-fous ajoutés dans `available()` / `accept()` (services et rides) :
      403 avec message clair si profil absent ✅

---

## 🟠 Priorité 4 — Fin de course et gains

- [x] `mark_delivered()` : `final_price` figé (= `estimated_price` à défaut) ✅
- [x] `CourierEarning` créé à la livraison (idempotent) : net = prix − frais de service (220)
      → cohérent avec l'écran mobile « Vous avez gagné +2 280 F » ✅
- [x] `client_rating` : vérifié, bien mis à jour par `rate()` ✅

---

## 🟡 Priorité 5 — Fonctionnalités à créer (non bloquantes, l'app affiche « Bientôt disponible »)

### Messagerie client ↔ coursier (écran F3) — ✅ RÉALISÉ
- [x] Modèle `services.Message` (request, sender, body, read_at) + migration `0003_message`
- [x] REST : `GET/POST /api/v1/services/{id}/messages/` (accès : client + coursier assigné,
      messages reçus marqués lus à l'ouverture du fil)
- [x] Mobile : `ChatScreen` (bulles, envoi optimiste, polling 3 s, ✓/✓✓) branché depuis
      E1, le suivi F1, le profil coursier E2 et l'écran coursier « Livraison en cours »
- [ ] (Amélioration future) Consumer websocket `ws/chat/{request_id}/` pour remplacer le polling

### Coursiers favoris (E4) — ✅ RÉALISÉ
- [x] Modèle `couriers.FavoriteCourier` + migration `0004_favoritecourier`
- [x] Endpoints : `GET /api/v1/favorites/couriers/`, `POST …/add/`, `POST …/remove/`
- [x] Mobile : `src/utils/favorites.ts` basculé sur l'API (cache AsyncStorage en secours hors ligne)

### Reçu PDF (écran H2) — ✅ RÉALISÉ
- [x] `GET /api/v1/services/{id}/receipt/` → PDF A5 (reportlab), livraisons terminées uniquement,
      auth par header OU `?token=` (ouverture navigateur depuis le mobile)
- [x] `reportlab` ajouté à `requirements/base.txt` → **`pip install reportlab`**
- [x] Mobile : bouton « 📄 Télécharger le reçu » actif (visible si statut `delivered`)

---

## ✅ Déjà conforme (aucune action)

- Auth OTP : `request`/`verify` (payload `phone`, `code`, `user_type` ; réponse
  `access`/`refresh`/`user`/`is_new_user`), refresh, logout, `auth/me/` GET+PATCH
- Services & rides : CRUD + `cancel`/`rate`/`available`/`accept`/`pickup`/`start`/`deliver`/`complete`
- Tracking : `POST tracking/location/`, `GET tracking/nearby/` (réponse `{workers, count}`
  avec `rating` — exactement ce que lit le mobile)
- Notifications : `read`, `read_all`, `unread_count`
- Paiements : `initiate`, `wallet`, `transactions`, `withdrawals`
- Fleet : `vehicles`, `vehicles/available`, `rentals`
- Couriers/Drivers : `me` (GET+PATCH), `go_online`, `go_offline`, `earnings`
  (forme `{results, total_net}` = celle attendue par l'écran Gains)
- WebSocket : `wss://…/ws/tracking/?token=<jwt>` + message `location.update`
  (le mobile envoie exactement ce format)

---

## Rappel — ce que le mobile envoie à la création d'un envoi

```json
POST /api/v1/services/
{
  "pickup_address": "…", "pickup_location": {"lat": 12.365, "lng": -1.533},
  "pickup_contact_name": "…", "pickup_contact_phone": "…",
  "delivery_address": "…", "delivery_location": {"lat": 12.37, "lng": -1.528},
  "delivery_contact_name": "…", "delivery_contact_phone": "…",
  "package_description": "Document", "package_size": "small",
  "is_fragile": false, "delivery_instructions": "…",
  "assignment_type": "broadcast",      // ⬅ à persister (P1)
  "broadcast_radius_km": 5,            // ⬅ à persister (P1)
  "payment_method": "cash",            // ⬅ à persister (P1)
  "estimated_price": 2500,             // ⬅ à recalculer serveur (P1)
  "distance_km": 6.4,                  // ✅ déjà accepté
  "preferred_courier": "<uuid>"        // ⬅ mode direct uniquement (P1)
}
```
