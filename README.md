# TeamFollowUP

Outil interne de pilotage d'une tribe organisée en **squads** (un cloud provider,
un service, un domaine data…). Chaque squad a un **responsable (leader)** qui saisit
sa **roadmap trimestrielle** (jalons par quarter + avancement) et ses **objectifs
annuels**. L'outil consolide tout dans un **dashboard de cartes** conçu pour faire
remonter ce qui dérape (le pire en haut), avec **historisation** et **suivi de la
fraîcheur** des données.

Charte graphique maison : `theme.css` à tokens (thème navy `#1E2761`, accent `#175CD3`).

## Documentation complète

La documentation produit/technique/ops **à jour et faisant foi** se trouve dans **[`docs/`](docs/README.md)** :
architecture (diagrammes Mermaid), [modèle de données + ERD](docs/03-data-model.md),
[référence API](docs/04-api-reference.md) (+ `docs/openapi.json`), [sécurité](docs/05-security.md),
[runbook d'exploitation](docs/06-operations-runbook.md), [guide développeur](docs/07-developer-guide.md),
[stratégie de tests](docs/08-testing-strategy.md), [rapport d'audit](docs/09-audit-report.md),
[dette & risques](docs/10-tech-debt-and-risk-register.md),
[roadmap & enterprise-readiness](docs/11-roadmap-and-enterprise-readiness.md),
le **[guide de déploiement (VMware, GCP, S3NS, AWS, Azure)](docs/12-deployment-guide.md)**, le
[banc Kubernetes de bout en bout avec Keycloak (OIDC et SAML)](docs/16-banc-kubernetes-sso.md)
et les [ADR](docs/adr/README.md).

> **Déploiement en production** (cloud ou on-prem) : voir le
> **[guide de déploiement](docs/12-deployment-guide.md)**. En prod, mettez
> `SEED_DEMO=false`, `COOKIE_SECURE=true`, `PUBLIC_BASE_URL` = l'adresse que les
> utilisateurs tapent (elle sert de base à toutes les URL de rappel SSO), et un
> `SECRET_KEY` / mot de passe DB issus d'un coffre de secrets.

> Note : certaines sections ci-dessous décrivent le produit initial ; en cas de divergence,
> **`docs/` fait référence** (ex. le statut RAG des objectifs est désormais *dérivé de l'avancement*,
> et l'accès aux sections est piloté par la matrice **Personas → capacités**).

## Démarrage en une commande

Prérequis : Docker + Docker Compose.

```bash
cp .env.example .env
docker compose up -d --build
```

Puis ouvrez **http://localhost:8000**. L'app sert l'UI et l'API sur ce **port
unique**, en **HTTP simple**, et laisse le **TLS à l'infrastructure** en amont
(Gateway API sur GKE, ALB, reverse proxy) : c'est le modèle recommandé et le
défaut. Pour un déploiement autonome sans infrastructure de terminaison TLS,
`TLS_ENABLED=true` fait terminer le TLS par l'app elle-même sur le port **8443**
(certificat auto-signé au premier démarrage, remplaçable depuis
**Administration → HTTPS / Certificats**). Dans les deux cas la redirection
HTTP→HTTPS n'est pas gérée par l'app.

> **Une seule URL à connaître.** Dès que l'application est déployée derrière une
> vraie adresse, renseignez `PUBLIC_BASE_URL` (ou le champ **URL publique** dans
> Administration → Authentification) : toutes les URL de rappel OIDC et SAML en
> sont dérivées. Voir « Brancher OIDC » plus bas.

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
- **Administration** (admin) : **navigation latérale groupée** (Organisation, Configuration,
  Authentification & Email, Modération & Journaux) ; CRUD squads (nom, responsable, ordre,
  **produits & hardware**), CRUD utilisateurs & rôles, modules, personas, réglages, journal
  d'audit. Gestion des squads aussi via **« Manage my squads »** (produits/hardware, budget,
  activation des KPIs).
- **Exports** : rapport imprimable / PDF (dashboard et par squad, format unifié, via
  l'impression du navigateur) et export CSV.
- **HTTPS optionnel dans l'app** (`TLS_ENABLED=true`, pour un déploiement sans
  infrastructure de terminaison TLS) : depuis **Administration → HTTPS / Certificats**,
  import d'un certificat **PEM + clé** ou **PFX/PKCS#12**, gestion des **CA racines et
  intermédiaires**, régénération auto-signée (CN/SAN).
- **API REST documentée** : Swagger sur **/docs** (`http://localhost:8000/docs` en local).

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
| `APP_HTTP_PORT` | `8000` | Port hôte (port unique de l'app, HTTP simple). |
| `TLS_ENABLED` | `false` *(valeur du `.env` livré)* | `true` = l'app termine le TLS elle-même sur `8443` (exposez alors `APP_HTTPS_PORT`). Non renseignée, l'app retombe sur `true`, d'où l'intérêt de la fixer explicitement. |
| `PUBLIC_BASE_URL` | *(vide → déduit de la requête)* | URL publique de l'app (`https://teamfollowup.exemple.com`). Base de toutes les URL de rappel SSO. |
| `COOKIE_SECURE` | `false` | Passez à `true` dès que l'app est publiée en HTTPS (y compris si le TLS est terminé en amont). |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `tribe` | Base PostgreSQL (interne). |
| `SECRET_KEY` | *(à changer)* | Clé de signature des sessions. |
| `STALENESS_THRESHOLD_DAYS` | `7` | Seuil de péremption (jours). |
| `SEED_DEMO` | `true` | Seed de démonstration au premier démarrage. |
| `BREAKGLASS_EMAIL` | `admin@local` | Email du compte de secours. |
| `BREAKGLASS_PASSWORD` | *(vide → aléatoire)* | Mot de passe du compte de secours. |
| `OIDC_ENABLED` + `OIDC_*` | `false` | Login OIDC (Authorization Code + PKCE). |
| `SAML_ENABLED` + `SAML_*` | `false` | Login SAML 2.0 (cible PingFederate). |

## L'URL publique, base de toute la configuration SSO

Les trois URL qu'un fournisseur d'identité réclame ne sont jamais à écrire à la
main : ce sont toujours l'**URL publique de l'application** suivie d'un chemin fixe.

| Ce que l'IdP demande | Valeur |
|----------------------|--------|
| URL de redirection OIDC | `<URL publique>/api/auth/oidc/callback` |
| Entity ID SAML (SP) | `<URL publique>/api/auth/saml/metadata` |
| ACS URL SAML | `<URL publique>/api/auth/saml/acs` |

L'URL publique est **l'adresse que vos utilisateurs saisissent dans leur navigateur**,
et non le port d'écoute du conteneur : derrière une Gateway, le pod parle HTTP sur
`:8000` alors que l'URL publique est `https://teamfollowup.exemple.com` sur le port 443.

Elle se définit à deux endroits, au choix :

- **Administration → Authentification**, champ « URL publique » (à chaud, sans
  redémarrage). L'écran affiche ensuite les trois URL ci-dessus **prêtes à copier**
  chez l'IdP, avec un bouton de copie.
- la variable `PUBLIC_BASE_URL` dans `.env` (utile pour un déploiement scripté).

Laissée **vide**, l'app déduit l'URL de chaque requête reçue, en tenant compte de
`X-Forwarded-Proto` / `X-Forwarded-Host` : c'est déjà correct en local et pour tout
déploiement joignable par une seule adresse. Renseignez-la dès que ce n'est plus le cas.

## Brancher OIDC

1. Renseignez l'**URL publique** (voir ci-dessus).
2. Déclarez une application cliente chez votre fournisseur d'identité, en y copiant
   l'URL de redirection affichée dans Administration → Authentification. Elle doit
   correspondre **à l'identique** : le moindre écart de host, de port ou de slash
   final fait échouer la connexion.
3. Dans `.env` : `OIDC_ENABLED=true`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`,
   `OIDC_CLIENT_SECRET`, `OIDC_SCOPES` (ou les mêmes champs dans l'écran d'administration).
   `OIDC_REDIRECT_URI` reste **vide** : il est dérivé de l'URL publique. Ne le
   renseignez que pour forcer une URL imposée par un enregistrement IdP existant.
4. `docker compose up -d`. Un bouton « Se connecter via OIDC » apparaît ; le compte
   est créé à la volée **en attente**, puis validé depuis le menu « Accès ».

## Brancher SAML / PingFederate

1. Renseignez l'**URL publique** (voir ci-dessus).
2. Côté PingFederate, créez une connexion SP avec l'**Entity ID** et l'**ACS URL**
   (binding HTTP-POST) affichés dans Administration → Authentification, ou importez
   directement les métadonnées SP publiées sur `<URL publique>/api/auth/saml/metadata`.
   **NameID** : e-mail ; **attributs** : `email`, `displayName`.
3. Dans `.env` : `SAML_ENABLED=true`, `SAML_IDP_METADATA_URL` (ou `_PATH`), et
   `SAML_SP_CERT` / `SAML_SP_KEY` si la signature est requise. `SAML_SP_ENTITY_ID`
   et `SAML_ACS_URL` restent **vides** (dérivés de l'URL publique).

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
