# Tribe Run Tracker

Outil interne de pilotage d'une tribe organisée en **squads** (un cloud provider,
un service, un domaine data…). Chaque squad a un **responsable (leader)** qui saisit
sa **roadmap trimestrielle** (jalons par quarter + avancement) et ses **objectifs
annuels**. L'outil consolide tout dans un **dashboard de cartes** conçu pour faire
remonter ce qui dérape (le pire en haut), avec **historisation** et **suivi de la
fraîcheur** des données.

Charte graphique alignée sur l'application RunAssessment (thème navy `#1E2761`).

## Démarrage en une commande

Prérequis : Docker + Docker Compose.

```bash
cp .env.example .env
docker compose up -d --build
```

Puis ouvrez **http://localhost:8080**.

Au premier démarrage, le conteneur `app` attend PostgreSQL, applique les migrations
Alembic, crée le **compte de secours** (breaking-glass) et applique le **seed de
démonstration** (9 squads, roadmaps trimestrielles, dont 2 squads à donnée périmée).
Seed désactivable via `SEED_DEMO=false`.

### Se connecter

| Persona | Identifiant | Mot de passe |
|---------|-------------|--------------|
| Compte de secours (admin) | `admin@local` | `changeme-admin` (valeur de `.env`) |
| Administrateur (démo) | `marie.tribe@local` | `demo` |
| Tribe leader | `nadia.n1@local` | `demo` |
| Squad leader | ex. `sara.gcp@local`, `ana.paiements@local` | `demo` |
| Membre (lecture seule) | `hugo.member@local` | `demo` |

> En tant qu'**administrateur**, utilisez le sélecteur « Voir en tant que » dans l'en-tête
> pour prévisualiser l'application telle que la voit chaque persona (aperçu en lecture seule).

> Si `BREAKGLASS_PASSWORD` est vide dans `.env`, un mot de passe aléatoire est
> généré et imprimé dans les logs : `docker compose logs app | grep -i secours`.

Tous les comptes de démonstration utilisent le mot de passe `demo`.

## Modèle

- **Squad** : liste plate, chaque squad a un **responsable** (squad leader) et une **équipe**
  (membres : fiches personnes, optionnellement reliées à un compte).
- **Roadmap** : des **jalons** rattachés à un **quarter** (`année` + `Q1..Q4`) avec un
  statut (planifié / en cours / livré / à risque / en retard). Chaque quarter porte un
  **curseur d'avancement** (0-100 %) saisi par le squad leader.
- **Objectifs** : annuels, statut RAG, **posés par le tribe leader** (lecture seule côté squad leader).
- En détail : **KPIs** chiffrés, **équipe / organigramme de la squad**, **historique** des
  soumissions + comparaison, **exports**.

## Fonctionnalités

- **Dashboard (accueil)** : compteurs globaux + **grille de grandes cartes par squad**, chaque
  carte affichant la pastille de statut, les **4 mini-barres Q1→Q4**, le détail des objectifs
  (R/A/V), les jalons livrés/en retard, le nombre de membres et la fraîcheur. Sélecteur
  d'**année**, filtres **statut / fraîcheur**. Clic → détail.
- **Détail squad** : roadmap par quarter, objectifs annuels, KPIs, **équipe (organigramme de
  la squad)**, historique + comparaison, exports.
- **Saisie (guidée)** : page unique avec bandeau explicatif et **checklist de complétion** ;
  édition de la roadmap (jalons + curseur), des KPIs et de l'**équipe** ; objectifs en lecture
  seule pour le squad leader ; bouton **« Soumettre »** → instantané immuable + fraîcheur.
- **Organigramme global** : arbre éditable de la tribe (un nœud peut être relié à une squad
  pour afficher son statut), **modifiable par le tribe leader** ; clic sur un nœud relié → détail.
- **Aperçu persona** : l'admin peut voir l'app « en tant que » chaque rôle (lecture seule).
- **Administration** (admin) : CRUD squads (nom, responsable, ordre), CRUD utilisateurs &
  rôles, réglage du seuil de fraîcheur, journal d'audit.
- **Exports** : rapport imprimable / PDF (dashboard et par squad, format unifié, via
  l'impression du navigateur) et export CSV.
- **API REST documentée** : Swagger sur **http://localhost:8080/docs**.

## Statut d'une squad (calculé côté serveur)

- **rouge / bloqué** si ≥1 jalon du **quarter courant** en retard, OU ≥1 objectif rouge,
  OU ≥2 objectifs orange ;
- sinon **orange / sous tension** si ≥1 jalon du quarter courant à risque, OU ≥1 objectif orange ;
- sinon **vert / tenu**.

La donnée est **périmée** si la dernière soumission dépasse le seuil (défaut 7 jours,
`STALENESS_THRESHOLD_DAYS`, modifiable dans Administration), indépendamment du statut.

## Personas / rôles

- **admin** : accès total ; seul à voir l'Administration et les Réglages. Peut prévisualiser
  l'application « en tant que » n'importe quelle persona (aperçu lecture seule).
- **tribe_leader** : crée et gère les squads, gère les membres, **définit les objectifs et leur
  statut**, construit et modifie l'**organigramme global** de la tribe.
- **squad_leader** : gère **sa** squad — roadmap (jalons + avancement), KPIs, membres ; soumet
  les cycles. Les objectifs lui sont en **lecture seule** (posés par le tribe leader).
- **member** : lecture seule de ce que voit un squad leader (dashboard, détail, organigramme).

## Variables d'environnement

Toutes les variables ont un défaut fonctionnel (voir `.env.example`).

| Variable | Défaut | Rôle |
|----------|--------|------|
| `APP_PORT` | `8080` | Port hôte d'exposition de l'app. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `tribe` | Base PostgreSQL (interne). |
| `SECRET_KEY` | *(à changer)* | Clé de signature des sessions. |
| `STALENESS_THRESHOLD_DAYS` | `7` | Seuil de péremption (jours). |
| `SEED_DEMO` | `true` | Seed de démonstration au premier démarrage. |
| `BREAKGLASS_EMAIL` | `admin@local` | Email du compte de secours. |
| `BREAKGLASS_PASSWORD` | *(vide → aléatoire)* | Mot de passe du compte de secours. |
| `OIDC_ENABLED` + `OIDC_*` | `false` | Login OIDC (Authorization Code + PKCE). |
| `SAML_ENABLED` + `SAML_*` | `false` | Login SAML 2.0 (cible PingFederate). |

## Brancher OIDC

1. Déclarez une application cliente chez votre fournisseur d'identité.
2. URL de redirection : `http://localhost:8080/api/auth/oidc/callback`.
3. Dans `.env` : `OIDC_ENABLED=true`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`,
   `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, `OIDC_SCOPES`.
4. `docker compose up -d`. Un bouton « Se connecter via OIDC » apparaît ; provisioning
   à la volée (rôle `viewer`), promu par un admin.

## Brancher SAML / PingFederate

1. Côté PingFederate, créez une connexion SP :
   - **Entity ID (SP)** : `http://localhost:8080/api/auth/saml/metadata`
   - **ACS URL** : `http://localhost:8080/api/auth/saml/acs` (HTTP-POST)
   - **NameID** : e-mail ; **attributs** : `email`, `displayName`.
2. Dans `.env` : `SAML_ENABLED=true`, `SAML_IDP_METADATA_URL` (ou `_PATH`),
   `SAML_SP_ENTITY_ID`, `SAML_ACS_URL`, et `SAML_SP_CERT`/`SAML_SP_KEY` si signature requise.
3. Métadonnées SP exposées sur `http://localhost:8080/api/auth/saml/metadata`.

Avec OIDC et SAML à `false`, l'application reste pleinement fonctionnelle via le compte de secours.

## Tests

```bash
docker compose run --rm app pytest
```

Couvrent : statut dominant (roadmap du quarter + objectifs), fraîcheur, avancement par
quarter, snapshot immuable + comparaison, et contrôle d'accès par rôle.

## Structure du dépôt

```
.
├── docker-compose.yml          # services app + db, volume persistant
├── Dockerfile                  # multi-stage : build React → runtime FastAPI
├── .env.example                # toutes les variables, commentées
├── README.md / DECISIONS.md / REFONTE_SPEC.md
├── backend/
│   ├── app/                    # FastAPI : models, routers, auth, seed, status
│   ├── alembic/                # migrations (appliquées au démarrage)
│   └── tests/                  # pytest
└── frontend/                   # React + Vite + TS (charte navy, sans Tailwind)
```

## Arrêt / réinitialisation

```bash
docker compose down            # arrête (données conservées)
docker compose down -v         # arrête et SUPPRIME les données (volume db)
```
