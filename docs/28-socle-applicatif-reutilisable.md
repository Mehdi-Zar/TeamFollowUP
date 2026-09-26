# 28 - Socle applicatif reutilisable

Ce document decrit le socle commun a toutes les applications de la famille : la pile,
les composants standard (authentification, autorisation, configuration, observabilite,
donnees, design), les garde-fous et la sequence de demarrage. Il est generique : aucun
concept metier de TeamFollowUP n'y est requis.

## 0. Comment s'en servir

1. Creer le depot de la nouvelle application, vide.
2. Y copier ce fichier sous le nom `CLAUDE.md` (il sert alors d'instructions permanentes
   a Claude Code) ou `SOCLE.md` si vous preferez garder un `CLAUDE.md` court qui y renvoie.
3. Ajouter en tete du fichier copie un encart de cinq lignes : nom de l'application,
   probleme qu'elle resout, objets metier principaux, roles qui l'utilisent, mode de
   deploiement. C'est la seule chose qui change d'une application a l'autre.
4. Dérouler la sequence du chapitre 10.

Le depot de reference est `TeamFollowUP`. Quand ce document dit "voir `app/deps.py`", le
fichier est a lire la-bas : il est la version eprouvee, pas un exemple reconstitue.

## 1. Les principes

1. **Un seul processus sert l'API et l'interface.** Le backend expose `/api/...` et sert la
   SPA compilee pour tout le reste, avec repli sur `index.html` pour le routage cote client.
   Un seul conteneur, un seul port, pas de CORS, pas de second deploiement.
2. **Un seul port en clair, le TLS est termine devant.** L'application ne porte pas de
   certificat : Gateway API, ALB ou reverse proxy s'en chargent. Elle lit
   `X-Forwarded-Proto` et `X-Forwarded-Host`.
3. **Une seule URL a configurer.** `PUBLIC_BASE_URL` est l'URL publique. Toutes les URLs de
   rappel SSO en decoulent. A vide, elles sont deduites de la requete entrante.
4. **Ce qui se regle sans redemarrer se regle en base.** Les reglages d'exploitation (SSO,
   SMTP, modules, personas, apparence, retention, export de journaux) vivent dans une table
   cle/valeur JSON editable depuis l'administration. L'environnement ne porte que ce qui est
   lu au demarrage (secrets, base de donnees, port, format de logs).
5. **Le controle d'acces est une dependance, jamais un `if` dans un handler.** Les gardes
   sont declaratives et testables.
6. **Toute mutation laisse une trace.** Une ligne d'audit est ajoutee dans la meme
   transaction que le changement metier.
7. **Les statuts sont derives, jamais stockes.** Ce qui se calcule a partir d'autre chose se
   calcule a la lecture, sinon deux verites coexistent.
8. **Aucune chaine en dur dans l'interface.** Tout passe par le dictionnaire i18n, FR et EN
   en parite, verifiee par les tests.
9. **La regle typographique vaut pour tout le depot** (chapitre 9), sans liste d'exceptions.
10. **La documentation fait partie du "fini".** Une fonctionnalite livree sans sa page de
    `docs/` n'est pas livree.

## 2. Pile technique

| Couche | Choix | Version de reference |
|---|---|---|
| Frontend | React, TypeScript, React Router, Vite, CSS maison (aucun framework UI) | React 19, TS 5, Vite 8 |
| Backend | FastAPI, Pydantic 2, SQLAlchemy 2, Uvicorn | FastAPI 0.115 |
| Base | PostgreSQL | 16 |
| Migrations | Alembic | 1.14 |
| Auth | cookie de session JWT (PyJWT), Argon2 (argon2-cffi), Authlib (OIDC), python3-saml (SAML) | |
| Observabilite | prometheus-client, logs JSON, tampon circulaire en memoire | |
| Documents | python-pptx, HTML rendu cote serveur, openpyxl pour les imports | |
| Emballage | Docker multi-etapes (build npm puis runtime Python) | node 22, python 3.12 |
| Tests | pytest, Vitest, Playwright | |

Regle de version : figer les versions exactes cote Python (`requirements.txt`), accepter les
correctifs cote npm (`^`), et laisser Dependabot proposer les montees.

## 3. Arborescence

```
.
├── CLAUDE.md                 conventions du depot (ce document, adapte)
├── Dockerfile                deux etapes : build SPA, runtime Python
├── docker-compose.yml        app + postgres, tout en variables d'environnement
├── .github/workflows/ci.yml  backend, frontend, e2e
├── backend/
│   ├── app/
│   │   ├── main.py           fabrique FastAPI : middlewares, routeurs, SPA
│   │   ├── server.py         lanceur (un port, HTTP simple)
│   │   ├── config.py         reglages lus de l'environnement
│   │   ├── database.py       moteur, session, Base
│   │   ├── models.py         ORM
│   │   ├── schemas.py        contrats Pydantic
│   │   ├── serializers.py    ORM vers DTO
│   │   ├── deps.py           authentification, RBAC, gardes
│   │   ├── rbac.py           modele de droits central
│   │   ├── security.py       Argon2 + jeton de session
│   │   ├── authconfig.py     SSO configurable a chaud
│   │   ├── oidc.py saml.py   flux SSO
│   │   ├── access.py         validation des comptes SSO
│   │   ├── *config.py        accesseurs typés sur app_settings
│   │   ├── logconfig.py logbuffer.py metrics.py logexport.py
│   │   ├── ops.py            diagnostic et redemarrage
│   │   ├── datasnapshots.py datareset.py maintenance.py
│   │   ├── routers/          un routeur par domaine
│   │   └── static/           SPA compilee (produite au build)
│   ├── alembic/versions/
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx main.tsx api.ts auth.tsx config.tsx i18n.tsx types.ts
│       ├── theme.css         jetons et classes du design system
│       ├── components/       ui.tsx, Layout.tsx, pageChrome.tsx, listView.tsx
│       └── pages/            une page par route, plus pages/admin/
├── docs/                     documentation numerotee + docs/adr/
└── e2e/                      Playwright
```

## 4. Socle backend

### 4.1 Configuration : deux etages

**Etage 1, l'environnement.** Un seul objet `Settings` (pydantic-settings), instancie une
fois, importe partout.

```python
# app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MonApp"
    secret_key: str = "change-me-in-prod-please-32chars-min-secret"
    session_cookie: str = "app_session"
    session_max_age_seconds: int = 60 * 60 * 12
    cookie_secure: bool = False          # true derriere TLS
    cookie_samesite: str = "lax"

    http_port: int = 8000
    public_base_url: str = ""            # vide : deduit de la requete

    log_format: str = "text"             # text | json
    log_level: str = "INFO"
    metrics_enabled: bool = True
    metrics_token: str = ""

    login_max_attempts: int = 10
    login_window_seconds: int = 300
    audit_retention_days: int = 0        # 0 : conservation illimitee

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "app"
    postgres_user: str = "app"
    postgres_password: str = "app"

    breakglass_email: str = "admin@local"
    breakglass_password: str = ""        # vide : genere et journalise au 1er demarrage

    @property
    def database_url(self) -> str:
        return (f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

**Etage 2, la base.** Une table `app_settings(key, value_json)` et un module d'accesseurs par
domaine. Le patron est toujours le meme : valeurs par defaut, fusion avec ce qui est stocke,
validation a l'ecriture, jamais de lecture brute du JSON ailleurs.

```python
# app/generalconfig.py (patron valable pour smtpconfig, authconfig, modulesconfig, ...)
import json
from sqlalchemy.orm import Session
from .models import AppSetting

KEY = "general"


def _defaults() -> dict:
    return {"default_lang": "fr", "staleness_threshold_days": 7}


def get_general(db: Session) -> dict:
    row = db.get(AppSetting, KEY)
    data = _defaults()
    if row and row.value:
        data.update(json.loads(row.value))
    return data


def set_general(db: Session, patch: dict) -> dict:
    data = get_general(db)
    data.update({k: v for k, v in patch.items() if k in _defaults()})
    row = db.get(AppSetting, KEY) or AppSetting(key=KEY)
    row.value = json.dumps(data)
    db.merge(row)
    db.commit()
    return data
```

Regle : **un reglage que l'exploitant doit pouvoir changer sans redemarrer va en base**. Un
reglage lu au demarrage (port, secret, base, format de logs) reste dans l'environnement, et
l'ecran Ops signale qu'un redemarrage est requis.

### 4.2 Base de donnees et migrations

- SQLAlchemy 2, `Base` declarative dans `database.py`, `get_db` en dependance FastAPI.
- **Alembic obligatoire** : aucune creation de schema implicite en production. L'entrypoint
  applique `alembic upgrade head` avant de demarrer l'API.
- Trois tables existent dans toutes les applications : `users`, `app_settings`, `audit_log`.
- Les tests tournent sur SQLite en memoire : eviter les types propres a Postgres dans le
  modele, et passer par `JSON` plutot que `JSONB` si la portabilite des tests compte.

### 4.3 Identite et sessions

Mots de passe en Argon2, session dans un JWT signe pose en cookie `HttpOnly`. Pas d'etat de
session cote serveur, donc pas de table a purger.

```python
# app/security.py
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from .config import settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, Exception):
        return False          # echec ferme : un hash casse n'authentifie jamais


def make_session(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now,
               "exp": now + timedelta(seconds=settings.session_max_age_seconds)}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_session(token: str) -> int | None:
    try:
        return int(jwt.decode(token, settings.secret_key, algorithms=["HS256"])["sub"])
    except Exception:
        return None
```

Cookie : `httponly=True`, `samesite` et `secure` pris des reglages, duree alignee sur le jeton.
Limitation de debit sur `/api/auth/login` (`login_max_attempts` par IP et par fenetre).

### 4.4 SSO et comptes de secours

Quatre voies d'entree, toutes presentes des la premiere version :

1. **OIDC** (Authlib, code d'autorisation avec PKCE), rappel sur `/api/auth/oidc/callback`.
2. **SAML 2.0** (python3-saml), metadonnees sur `/api/auth/saml/metadata`, assertion sur
   `/api/auth/saml/acs`.
3. **Mot de passe local**, utile hors entreprise et pour les tests.
4. **Compte de secours (break-glass)**, cree et force en administrateur a chaque demarrage,
   qui se connecte toujours par `POST /api/auth/login` meme si le formulaire est masque.
   C'est le seul recours quand le SSO tombe ou qu'un reglage verrouille l'administration.

Regles structurantes :

- **Les URLs de rappel sont derivees** de l'URL publique, jamais saisies trois fois :

```python
SSO_URL_PATHS = {
    "oidc_redirect_uri": "/api/auth/oidc/callback",
    "saml_sp_entity_id": "/api/auth/saml/metadata",
    "saml_acs_url": "/api/auth/saml/acs",
}
```

  Une surcharge manuelle qui redit la valeur derivee est ramenee a "vide" a l'enregistrement,
  pour qu'elle continue de suivre l'URL publique.
- **La configuration SSO se fait dans l'interface**, pas seulement par variables. Le module
  correspondant (`authconfig.py`) lit la base et retombe sur l'environnement.
- **Un test de connectivite** est fourni dans l'administration (resolution du `.well-known`,
  verification du client, lecture des metadonnees IdP) : sans lui, un SSO en panne se debogue
  a l'aveugle, et en production il n'y a ni shell ni base.
- **Le rattachement se fait par email** : un compte cree a l'avance (import, invitation)
  herite de son role et de ses affectations a la premiere connexion IdP.
- **Les nouveaux comptes SSO arrivent "en attente"** et doivent etre valides par un
  gestionnaire, avec un ecran de file d'attente et une portee de validation limitee aux
  droits du validateur (`access.py`). Le refus desactive le compte et le conserve pour l'audit.

### 4.5 Autorisation : trois axes orthogonaux

1. **Roles** hierarchiques, poses sur l'utilisateur, du plus au moins capable. Quatre suffisent
   dans la plupart des cas : `admin`, deux niveaux intermediaires, `member`. Le fichier
   `rbac.py` est le seul endroit qui repond "cet acteur peut-il cette action sur cet objet".
2. **Personas et capacites** : une matrice, editable en administration, qui dit quelles
   **sections** de l'application chaque persona peut ouvrir. Les personas integres reprennent
   les roles, et l'admin peut en creer d'autres. Refus par defaut : une capacite absente du
   payload devient `False`.
3. **Modules** : des interrupteurs par service et par sous-fonction, stockes en base, exposes
   a la SPA par `/api/config` et appliques cote serveur. Ils permettent de livrer une
   fonctionnalite eteinte, puis de l'allumer par instance.

```python
# app/deps.py, extrait du patron de gardes
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise HTTPException(401, "Non authentifie")
    user_id = decode_session(token)
    user = db.get(User, user_id) if user_id else None
    if user is None or user.status != "active":
        raise HTTPException(401, "Session invalide")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ADMIN:
        raise HTTPException(403, "Reserve aux administrateurs")
    return user


def require_module(module: str, feature: str | None = None):
    """404 et non 403 : un module eteint n'existe pas, il ne se devine pas."""
    def guard(db: Session = Depends(get_db)):
        if not is_feature_enabled(db, module, feature):
            raise HTTPException(404, "Introuvable")
    return Depends(guard)
```

Convention de nommage : `can_*` renvoie un booleen (pour brancher), `assert_*` et `require_*`
levent une `HTTPException` (pour garder une route). Une ressource qui doit rester invisible
repond 404, pas 403.

### 4.6 Audit

```python
def record_audit(db, user_id, action, entity=None, entity_id=None, detail=None) -> None:
    """Ajoute la ligne sans commit : elle vit ou meurt avec la transaction metier."""
    db.add(AuditLog(user_id=user_id, action=action, entity=entity,
                    entity_id=str(entity_id) if entity_id is not None else None,
                    detail=detail))
```

Toute route qui ecrit appelle `record_audit`. L'administration offre une consultation
filtrable, et la retention est reglable (`audit_retention_days`, 0 pour illimite).

### 4.7 Observabilite

- **Logs** : lignes lisibles en local, JSON structure (severite, message, horodatage) quand
  `LOG_FORMAT=json`, ce que les agents de collecte lisent directement sur la sortie standard.
- **Metriques** : un middleware ASGI pur, enregistre en dernier donc le plus externe, mesure
  chaque requete et etiquette par **gabarit de route** (jamais le chemin brut, sinon le nombre
  de series explose). `/metrics` au format Prometheus, protege par jeton ou non route
  publiquement.
- **Tampon de logs en memoire** : un `logging.Handler` circulaire (2000 entrees) alimente un
  panneau Ops qui affiche, filtre et telecharge les journaux recents, et regle le niveau de log
  a chaud. Indispensable quand l'exploitant n'a acces qu'au web.
- **Export du journal d'audit** vers syslog, un bucket ou un entrepot, configurable en base.
- **Sante** : `GET /api/health` sans authentification, utilise par le conteneur, par la CI et
  par la sequence de redemarrage de l'interface.

### 4.8 Ops : redemarrer depuis l'application

Un panneau d'administration reserve aux administrateurs donne l'etat d'execution (version,
reglages lus au demarrage, base, planificateur) et un bouton de redemarrage. Le redemarrage
consiste a **sortir proprement du processus** : c'est l'orchestrateur (`restart: unless-stopped`
en Docker, `restartPolicy: Always` en Kubernetes) qui relance avec la nouvelle configuration.
Une variable (`OPS_DISABLE_RESTART=1`) le neutralise pour les tests.

### 4.9 Donnees : reprise, remise a zero, retention, imports

- **Instantanes** : prendre, lister, restaurer un instantane des donnees metier, avec
  planification. La sauvegarde de la base reste la reference, mais l'instantane se declenche
  depuis l'interface, donc il est utilisable par quelqu'un qui n'a pas la main sur le serveur.
- **Remise a zero granulaire** : choisir ce qu'on efface, garder la configuration. Evite le
  "je repars d'une base vide" qui detruit aussi le SSO et les personas.
- **Retention** : une tache periodique supprime ce qui a depasse sa duree de conservation, par
  type de donnee, opt-in (0 signifie conserver).
- **Import Excel** : pour toute donnee de masse, fournir un classeur telechargeable, rempli par
  l'utilisateur, televerse par l'administration et analyse en memoire, sans redeploiement.
  Patron : un module `import_*.py` qui expose `template_bytes()`, `read_upload(nom, contenu)` et
  `import_*(db, data)` idempotent par cle naturelle, plus un resume `{crees, mis a jour,
  avertissements}`. **Les avertissements sont obligatoires** : un import qui ne compte que ses
  succes se lit comme un succes, alors qu'une ligne rattachee a rien est invisible ensuite.
  Les colonnes se lisent **par position**, pour que l'entete puisse etre traduit.

### 4.10 Emails et taches de fond

- SMTP configurable en base, envoi "au mieux" qui n'echoue jamais la requete metier.
- Un planificateur dans le processus : une tache asynchrone demarree apres le demarrage, qui
  boucle a l'heure, avec chaque traitement **idempotent par periode** (semaine ISO, mois) pour
  qu'un redemarrage ne renvoie pas deux fois. `DISABLE_SCHEDULER=1` le coupe pour les tests.
  Passer a un ordonnanceur externe seulement quand plusieurs repliques tournent.

### 4.11 Cles d'API

Des cles machine pour l'API de lecture, avec portees, stockees hachees, revocables, et
declarees dans l'OpenAPI en schema `bearer` pour que le bouton **Authorize** de Swagger
fonctionne. La securite est declaree optionnelle (`[{}, {ApiKeyAuth: []}]`) pour que les appels
par cookie continuent de marcher.

## 5. Socle frontend

### 5.1 Structure

- `src/pages/` : un fichier par route. L'administration fait exception : une seule route, une
  coquille (`AdminPage.tsx`) qui resout les droits et l'onglet, et des panneaux independants
  dans `src/pages/admin/`, regroupes par famille.
- `src/components/` : les primitives partagees, jamais de composant metier isole dans une page
  si une deuxieme page peut en avoir besoin.
- Un test de bout en bout ouvre **toutes** les sections d'administration et verifie qu'elles
  s'affichent : c'est ce qui empeche la coquille de se disloquer quand les panneaux se
  multiplient.

### 5.2 Les trois contextes

- **`api.ts`** : client `fetch` unique, `credentials: "include"`, JSON, gestion du 204, et une
  `ApiError` typee qui porte le `status` pour que l'appelant branche sur 401.
- **`auth.tsx`** : qui est connecte, ses capacites, la file de validation d'acces, et les
  actions (connexion, deconnexion, endossement d'identite). `can(cap)` **refuse par defaut**.
- **`config.tsx`** : la configuration publique (nom, langue par defaut, apparence, carte des
  modules) recuperee de `/api/config`, avec des valeurs par defaut pour que l'interface
  s'affiche avant la reponse et n'eteigne jamais une fonction par accident.

### 5.3 i18n

Un dictionnaire FR et EN, un `useI18n().t(cle, vars)` qui interpole `{nom}`, et la langue du
visiteur (choix persiste) qui l'emporte sur la langue par defaut de l'instance. Trois regles
tenues par les tests :

- parite stricte des cles entre FR et EN ;
- toute cle utilisee existe, et **toute cle du dictionnaire est atteinte** (les cles construites
  dynamiquement sont detectees par leur prefixe) ;
- aucune chaine visible ecrite en dur dans un composant.

### 5.4 Design system

Pas de framework UI. Un fichier `theme.css` porte les jetons et les classes, et l'interface se
construit avec. Palette de reference (sobre, professionnelle) :

```css
:root {
  --navy: #1E2761;        /* identite, titres, boutons primaires */
  --navy-deep: #141B47;   /* survol du primaire */
  --ice-blue: #CADCFC;    /* aplats, selections */
  --ice-soft: #E8F0FE;    /* fonds de survol */
  --accent: #175CD3;      /* liens et actions secondaires */
  --green: #027A48;       /* etat favorable */
  --orange: #B54708;      /* vigilance */
  --red: #B42318;         /* alerte */
  --text: #1E293B;
  --grey: #64748B;        /* texte secondaire */
  --line: #E2E8F0;        /* filets et bordures */
  --bg: #F5F7FA;          /* fond de page */
  --radius: 14px;
  --shadow: 0 1px 3px rgba(20,27,71,.08), 0 6px 16px rgba(20,27,71,.06);
}

body {
  font-family: var(--font-family, Calibri, Carlito, "Segoe UI", system-ui, sans-serif);
  font-size: calc(1rem * var(--font-scale, 1));
  color: var(--text);
  background: var(--bg);
}
```

Regles de composition :

- **La carte est l'unite de mise en page** : fond blanc, `--radius`, `--shadow`, 20px de
  remplissage. Une page est une pile de cartes, pas un tableau de bord dense.
- **Boutons** : un primaire plein `--navy`, un secondaire blanc a bordure `--line`, un
  fantome transparent. Rayon 10px, 600 de graisse, pas plus d'un primaire par zone.
- **Etats** : un point de couleur ou une pastille, jamais une ligne entiere coloree.
- **Personnalisation a chaud** : les couleurs, logos, typographie et densite sont ecrits comme
  variables CSS sur l'element racine a partir de la configuration serveur. Ce qui est retire
  redevient la valeur de `theme.css`, donc pas de feuille injectee a nettoyer.

Primitives a fournir des le debut (`components/ui.tsx`) : `Modal`, `SectionCard`,
`Collapsible`, `StatusBadge`, `ProgressBar`, `Spinner`, `ErrorBanner`, `EmptyState`.
Y ajouter `Layout.tsx` (navigation, barre haute), `pageChrome.tsx` (une page publie son titre,
ses onglets et ses actions vers la barre haute) et `listView.tsx` (recherche, tri, densite,
memorises par ecran).

### 5.5 Regles d'ergonomie

- **Une seule entree de menu par sujet.** Deux ecrans qui font presque la meme chose se
  fusionnent.
- **Afficher les sections vides** avec un `EmptyState` explicite, pour que l'utilisateur voie
  ce qui existe.
- **Ouvrir les documents dans une fenetre de l'application**, pas dans un nouvel onglet.
- **Sobre** : pas d'emoji, pas d'icone decorative, pas de degrade.
- Vocabulaire : choisir un terme par concept et le tenir dans tout le produit et la doc.

## 6. Contrats transverses

Endpoints presents dans toutes les applications :

| Route | Role |
|---|---|
| `GET /api/health` | vivant, sans authentification |
| `GET /api/config` | configuration publique : nom, langue, apparence, modules |
| `GET /api/auth/config` | quelles voies de connexion sont ouvertes |
| `POST /api/auth/login`, `POST /api/auth/logout` | mot de passe local et compte de secours |
| `GET /api/auth/oidc/login`, `GET /api/auth/oidc/callback` | OIDC |
| `GET /api/auth/saml/metadata`, `POST /api/auth/saml/acs` | SAML |
| `GET /api/auth/me`, `GET /api/auth/permissions` | session et capacites |
| `GET /metrics` | metriques Prometheus, non routee publiquement |
| `GET /docs` | Swagger, avec bouton Authorize pour les cles d'API |

L'OpenAPI est **fige dans le depot** (`docs/openapi.json`) et la CI verifie qu'il est a jour :
une signature qui bouge sans qu'on le veuille se voit en revue.

## 7. Tests et garde-fous

| Suite | Commande | Ce qu'elle protege |
|---|---|---|
| Backend | `cd backend && pytest` | metier, RBAC, SSO, imports, rendus, retention |
| Frontend | `cd frontend && npm test` | i18n (parite, usage), typographie, composants |
| Types | `npx tsc --noEmit` | contrats TypeScript |
| Bout en bout | Playwright sur la pile Docker reelle | parcours complets, ouverture de tous les ecrans d'administration |

Garde-fous a reprendre tels quels, ils coutent peu et rattrapent beaucoup :

1. **Defauts non securises** : un test echoue si une valeur de production dangereuse (secret par
   defaut, cookie non securise, mot de passe de secours vide en mode SSO) passe en configuration
   reelle.
2. **Parite interface et API** : les capacites et modules connus du frontend sont exactement ceux
   que le backend expose.
3. **Typographie** : balayage de tout le depot.

```python
# backend/tests/test_typography.py, coeur du test
BANNED = {"\u2014": "em dash", "\u00b7": "middot"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", "dist", "static", ".venv", ".venv-test"}
SUFFIXES = {".py", ".ts", ".tsx", ".md", ".html", ".css", ".json", ".yml", ".yaml", ".sh", ".txt"}
# les caracteres sont ecrits en echappement pour que le test passe sa propre regle
```

Un troisieme test lit les **documents reellement produits** (HTML, PPTX, XLSX) : aucun controle
sur le code source ne peut prouver ce qu'une chaine formatee assemble.

**Definition du fini**, a chaque changement : types propres, build vert, `pytest` vert, parite
i18n, migration ajoutee si le schema bouge, `docs/` mis a jour.

## 8. Emballage, integration continue, deploiement

- **Dockerfile en deux etapes** : `node` compile la SPA, `python:3.12-slim` l'embarque dans
  `app/static`. Une image, un artefact, pas de decalage possible entre front et back.
- **Entrypoint** : attendre la base, `alembic upgrade head`, initialisation (compte de secours,
  jeu de demonstration optionnel), puis lancement. Les migrations s'appliquent donc toutes
  seules au demarrage.
- **docker-compose** : `app` et `db`, avec `healthcheck` sur la base et `depends_on: condition:
  service_healthy`. Toutes les valeurs en variables d'environnement avec defauts.
- **CI** en trois jobs : backend (pytest avec plancher de couverture en cliquet, plus verification
  de l'instantane OpenAPI), frontend (types, tests, build), bout en bout (compose puis Playwright).
- **Deploiement** : TLS devant, `PUBLIC_BASE_URL` renseigne, `COOKIE_SECURE=true`,
  `LOG_FORMAT=json`, `/metrics` non routee publiquement, secrets hors image.
- Le changement de front ou de back implique une **reconstruction de l'image** : editer un
  fichier source ne change rien a ce que sert le conteneur.

## 9. Conventions de redaction et de commit

- **Jamais de tiret cadratin (U+2014) ni de point median (U+00B7)** dans tout le depot : code,
  commentaires, docstrings (FastAPI les publie dans l'OpenAPI et dans Swagger), documentation,
  libelles, documents generes. Remplacer par une virgule, un deux-points, des parentheses, un
  retour a la ligne ou une simple espace. Rien qui "fasse IA" dans le rendu.
- Messages de commit courts, en francais, descriptifs, **sans mention d'outil ni de
  co-auteur**, et sans dossier d'outil dans le depot.
- La documentation suit le code dans le meme lot : jeu numerote dans `docs/` (produit,
  architecture, modele de donnees, API, securite, exploitation, guide developpeur, tests,
  deploiement) et un ADR par decision structurante dans `docs/adr/`.
- Un ADR tient en une page : contexte, decision, consequences, alternatives ecartees.

## 10. Sequence de demarrage d'une nouvelle application

A derouler dans l'ordre. Chaque lot se termine par une application qui demarre.

**Lot 0, le cadre.** Nom, probleme resolu, objets metier, roles, deploiement. Ecrire ces cinq
lignes en tete du `CLAUDE.md` copie, plus `docs/01-product-overview.md`.

**Lot 1, la carcasse.** Depot, Dockerfile deux etapes, compose, `main.py` qui sert `/api/health`
et la SPA, `theme.css`, `Layout`, une page vide. Objectif : `docker compose up -d --build`
affiche un ecran.

**Lot 2, identite et acces.** `users`, `app_settings`, `audit_log`, Argon2, session JWT, compte
de secours, connexion par mot de passe, `deps.py` avec les gardes, `rbac.py`. Objectif : se
connecter, voir son profil, etre refuse ailleurs.

**Lot 3, le metier.** Modele, migrations, routeurs, schemas, serializers, ecrans. C'est le seul
lot specifique a l'application : tout le reste est du socle.

**Lot 4, l'exploitation.** Console d'administration (coquille et panneaux), modules, personas,
configuration generale, SMTP, apparence, journal d'audit, panneau Ops avec logs et redemarrage,
instantanes et remise a zero.

**Lot 5, l'entreprise.** OIDC, SAML, test de connectivite, file de validation des comptes,
export du journal d'audit, cles d'API, metriques, retention.

**Lot 6, la finition.** i18n FR et EN complets, imports Excel si besoin, exports HTML et PPTX si
besoin, tests de bout en bout, documentation numerotee, ADR.

**Amorce a donner a Claude Code dans le nouveau depot** :

> Lis `CLAUDE.md` (socle applicatif). Nous construisons `<nom>`, qui `<probleme>`. Objets
> metier : `<liste>`. Roles : `<liste>`. Demarre par le lot 1 puis le lot 2 du chapitre 10,
> en reprenant les composants du socle a l'identique (configuration a deux etages, Argon2 et
> session JWT, gardes en dependances, audit sur les mutations, jetons CSS). Le depot de
> reference a copier est `C:\Claude\TeamFollowUP`. Propose le modele de donnees avant d'ecrire
> les migrations.

## 11. Check-list avant la premiere mise en ligne

- [ ] `SECRET_KEY` propre, `COOKIE_SECURE=true`, `PUBLIC_BASE_URL` renseigne.
- [ ] Mot de passe du compte de secours defini et range dans un coffre.
- [ ] SSO teste depuis l'ecran de diagnostic, URLs de rappel declarees chez l'IdP.
- [ ] `/metrics` non joignable publiquement, ou protegee par jeton.
- [ ] `LOG_FORMAT=json`, niveau de log par defaut `INFO`.
- [ ] Migrations appliquees, instantane initial pris, sauvegarde de base planifiee.
- [ ] Retention decidee pour le journal d'audit et les donnees personnelles.
- [ ] Les trois suites de tests vertes et l'instantane OpenAPI a jour.
- [ ] `docs/` complet, ADR des decisions prises.
- [ ] Aucun nom d'organisation reelle dans les jeux de donnees d'exemple.

## 12. Ce qu'il ne faut pas reprendre

Le socle s'arrete au chapitre 8. Tout ce qui, dans TeamFollowUP, parle de tribus, de squads,
d'objectifs, de jalons, d'engagements annuels, de comite de pilotage, d'humeur d'equipe ou de
rapport hebdomadaire est **du metier**, pas du socle : ne pas le porter par habitude. En
revanche, les **patrons** qui les portent se reprennent tels quels : statut derive et non
stocke, rendu de document cote serveur, import Excel idempotent, ecran de saisie guide en
plusieurs etapes, listes avec recherche et tri memorises.
