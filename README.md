# Tribe Run Tracker

Outil interne de pilotage d'une tribe organisée en **squads** (un cloud provider,
un service, un domaine data…). Chaque squad a un **responsable (leader)** qui saisit
sa **roadmap trimestrielle** (jalons par quarter + avancement) et ses **objectifs
annuels**. L'outil consolide tout dans un **dashboard de cartes** conçu pour faire
remonter ce qui dérape (le pire en haut), avec **historisation** et **suivi de la
fraîcheur** des données.

Charte graphique alignée sur l'application RunAssessment (thème navy `#1E2761`).

## Documentation complète

La documentation produit/technique/ops **à jour et faisant foi** se trouve dans **[`docs/`](docs/README.md)** :
architecture (diagrammes Mermaid), [modèle de données + ERD](docs/03-data-model.md),
[référence API](docs/04-api-reference.md) (+ `docs/openapi.json`), [sécurité](docs/05-security.md),
[runbook d'exploitation](docs/06-operations-runbook.md), [guide développeur](docs/07-developer-guide.md),
[stratégie de tests](docs/08-testing-strategy.md), [rapport d'audit](docs/09-audit-report.md),
[dette & risques](docs/10-tech-debt-and-risk-register.md),
[roadmap & enterprise-readiness](docs/11-roadmap-and-enterprise-readiness.md),
le **[guide de déploiement (VMware · GCP · S3NS · AWS · Azure)](docs/12-deployment-guide.md)** et les
[ADR](docs/adr/README.md).

> **Déploiement en production** (cloud ou on-prem) : voir le
> **[guide de déploiement](docs/12-deployment-guide.md)**. En prod, mettez
> `SEED_DEMO=false`, `COOKIE_SECURE=true`, et un `SECRET_KEY` / mot de passe DB
> issus d'un coffre de secrets.

> Note : certaines sections ci-dessous décrivent le produit initial ; en cas de divergence,
> **`docs/` fait référence** (ex. le statut RAG des objectifs est désormais *dérivé de l'avancement*,
> et l'accès aux sections est piloté par la matrice **Personas → capacités**).

## Démarrage en une commande

Prérequis : Docker + Docker Compose.

```bash
cp .env.example .env
docker compose up -d --build
```

Puis ouvrez **https://localhost:8443** (le site est servi en **HTTPS** sur ce
**port unique**, avec un certificat **auto-signé** par défaut - votre navigateur
affichera un avertissement, c'est normal ; acceptez-le). L'app ne gère pas de
redirection HTTP→HTTPS : c'est le rôle de l'infrastructure en amont (ex. Gateway
API sur GKE). Vous pouvez importer votre propre certificat (PEM/PFX)
et gérer les CA racines/intermédiaires depuis **Administration → HTTPS / Certificats**.

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

- **Squad** : liste plate, chaque squad a un **responsable** (squad leader), une **équipe**
  (membres : fiches personnes, optionnellement reliées à un compte), un ou plusieurs
  **produits** et, en option, du **hardware**.
- **Roadmap** : des **jalons** rattachés à un **quarter** (`année` + `Q1..Q4`) avec un
  statut (planifié / en cours / livré / à risque / en retard). Chaque quarter porte un
  **curseur d'avancement** (0-100 %) saisi par le squad leader.
- **Objectifs** : annuels, statut RAG, **posés par le tribe leader** (lecture seule côté squad leader).
- En détail : **KPIs** chiffrés, **équipe / organigramme de la squad**, **historique** des
  soumissions + comparaison, **exports**.
- **Comitologie** (optionnelle, module *Comitologie* désactivé par défaut) : le squad leader
  déclare les **comités récurrents** de sa squad (nom, objectif, fréquence, jour, heure, durée,
  participants), présentés en **tableau** avec édition en modale ; le tribe leader en a la
  **visibilité**. Activable depuis Administration → Services.

## Fonctionnalités

- **Dashboard (accueil)** : compteurs globaux + **grille de grandes cartes par squad**, chaque
  carte affichant la pastille de statut, les **4 mini-barres Q1→Q4**, le détail des objectifs
  (R/A/V), les jalons livrés/en retard, le nombre de membres et la fraîcheur. Sélecteur
  d'**année**, filtres **statut / fraîcheur**. Clic → détail.
- **Détail squad** : en-tête avec **produits & hardware** de la squad + le squad leader ;
  **OTD** (objectifs annuels engagés), **roadmap détaillée** par quarter, **messages clés**
  (succès / alerte / risque, horodatés), **budget** (total / consommé / prévision + statut
  RAG, visible uniquement par l'admin, le tribe leader et le squad leader concerné), KPIs,
  **équipe (organigramme)**, historique + comparaison, **exports HTML & PPTX** au rendu
  fidèle à l'écran.
- **Saisie (guidée)** : page unique avec bandeau explicatif et **checklist de complétion** ;
  édition de la roadmap (jalons + curseur), des KPIs et de l'**équipe** ; objectifs en lecture
  seule pour le squad leader ; bouton **« Soumettre »** → instantané immuable + fraîcheur.
- **Organigramme global** : arbre éditable de la tribe (un nœud peut être relié à une squad
  pour afficher son statut), **modifiable par le tribe leader** ; clic sur un nœud relié → détail.
- **Aperçu persona** : l'admin peut voir l'app « en tant que » chaque rôle (lecture seule).
- **Administration** (admin) : **navigation latérale groupée** (Organisation · Configuration ·
  Authentification & Email · Modération & Journaux) ; CRUD squads (nom, responsable, ordre,
  **produits & hardware**), CRUD utilisateurs & rôles, modules, personas, réglages, journal
  d'audit. Gestion des squads aussi via **« Manage my squads »** (produits/hardware, budget,
  activation des KPIs).
- **Exports** : rapport imprimable / PDF (dashboard et par squad, format unifié, via
  l'impression du navigateur) et export CSV.
- **HTTPS natif** : le site est servi en **HTTPS** (certificat **auto-signé** par
  défaut). Depuis **Administration → HTTPS / Certificats** : import d'un certificat
  **PEM + clé** ou **PFX/PKCS#12**, gestion des **CA racines et intermédiaires**,
  régénération auto-signée (CN/SAN). Application **à chaud**, sans redémarrage.
- **API REST documentée** : Swagger sur **https://localhost:8443/docs**.

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
- **squad_leader** : gère **sa** squad - roadmap (jalons + avancement), KPIs, membres ; soumet
  les cycles. Les objectifs lui sont en **lecture seule** (posés par le tribe leader).
- **member** : lecture seule de ce que voit un squad leader (dashboard, détail, organigramme).

## Variables d'environnement

Toutes les variables ont un défaut fonctionnel (voir `.env.example`).

| Variable | Défaut | Rôle |
|----------|--------|------|
| `APP_HTTPS_PORT` | `8443` | Port hôte HTTPS (port unique de l'app). |
| `COOKIE_SECURE` | `true` | Cookies de session en `Secure` (HTTPS actif par défaut). |
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
2. URL de redirection : `https://localhost:8443/api/auth/oidc/callback` (adaptez
   host/port à votre exposition réelle).
3. Dans `.env` : `OIDC_ENABLED=true`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`,
   `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, `OIDC_SCOPES`.
4. `docker compose up -d`. Un bouton « Se connecter via OIDC » apparaît ; provisioning
   à la volée (rôle `viewer`), promu par un admin.

## Brancher SAML / PingFederate

1. Côté PingFederate, créez une connexion SP :
   - **Entity ID (SP)** : `https://localhost:8443/api/auth/saml/metadata`
   - **ACS URL** : `https://localhost:8443/api/auth/saml/acs` (HTTP-POST)
   - **NameID** : e-mail ; **attributs** : `email`, `displayName`.
2. Dans `.env` : `SAML_ENABLED=true`, `SAML_IDP_METADATA_URL` (ou `_PATH`),
   `SAML_SP_ENTITY_ID`, `SAML_ACS_URL`, et `SAML_SP_CERT`/`SAML_SP_KEY` si signature requise.
3. Métadonnées SP exposées sur `https://localhost:8443/api/auth/saml/metadata`.

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
├── README.md / DECISIONS.md
├── docs/                       # doc produit/tech/ops (faisant foi) + guide de déploiement (12)
├── backend/
│   ├── app/                    # FastAPI : models, routers, auth, seed, status, report
│   ├── alembic/                # migrations (appliquées au démarrage)
│   ├── scripts/                # scripts ponctuels (seed de l'org réel, prune users)
│   └── tests/                  # pytest
└── frontend/                   # React + Vite + TS (charte navy, sans Tailwind)
```

## Arrêt / réinitialisation

```bash
docker compose down            # arrête (données conservées)
docker compose down -v         # arrête et SUPPRIME les données (volume db)
```
