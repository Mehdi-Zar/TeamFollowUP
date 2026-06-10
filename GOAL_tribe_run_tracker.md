# GOAL — Tribe Run Tracker (livraison autonome, produit fini dockerisé)

## 0. Mode d'exécution (NON NÉGOCIABLE)

Tu es en **goal mode autonome**. Règles impératives :

- **Ne demande AUCUNE validation, AUCUNE confirmation, AUCune clarification.** Si un choix est ambigu, tranche toi-même en suivant le principe « le plus simple qui satisfait la spec » et documente la décision dans `DECISIONS.md`.
- Livre un **produit complet et fini**, pas un squelette ni un MVP « à compléter ».
- Le critère de réussite final est unique et binaire : **`docker compose up -d` démarre l'application complète, et elle est immédiatement utilisable sur `http://localhost:8080` sans aucune étape manuelle supplémentaire.**
- Tu ne t'arrêtes pas tant que tous les critères d'acceptation de la section 9 ne sont pas vérifiés par toi-même (tu lances réellement les commandes, tu lis les logs, tu corriges, tu re-testes).
- Travaille en boucle build → run → test → fix jusqu'au vert complet.

---

## 1. Contexte métier

Outil interne de **pilotage d'une tribe** (organisation produit, ~9 équipes). Le commanditaire est le **Tribe Leader (N+1)** ; l'utilisateur principal qui administre l'outil est son **adjoint / numéro 2**. Chaque **responsable d'équipe** saisit périodiquement l'état de son équipe sur une interface web ; l'outil consolide tout dans un **dashboard unique** dont le but premier est de **détecter ce qui dérape**, pas de produire de longs comptes-rendus.

Spécificités à respecter :

- Les **rythmes de suivi sont hétérogènes** (certaines équipes hebdo, d'autres bi-mensuel). L'outil doit donc **horodater chaque saisie** et afficher en permanence la **fraîcheur de la donnée** (« mis à jour il y a N jours », et marquage visuel « périmé » au-delà d'un seuil configurable, défaut 7 jours).
- Le N+1 veut savoir, par équipe : est-ce que les **objectifs**, **livrables** et **KPI** qu'il a fixés sont tenus.
- **Inversion de la pyramide** : l'écran d'accueil est la vue de consolidation où le pire remonte en haut automatiquement. Le détail est secondaire (accessible en drill-down).

## 2. Modèle de données

Postgres. Schéma minimal (adapter/enrichir librement) :

- **team** : id, name, description, parent_team_id (nullable, pour hiérarchie), lead_user_id, hierarchy_level (`N-1` | `N-2`), cadence (`weekly` | `biweekly`), display_order.
- **user** : id, email, display_name, role (`admin` | `lead` | `viewer`), auth_subject (sujet OIDC/SAML), is_break_glass (bool), password_hash (nullable, uniquement pour breaking-glass), created_at, last_login_at.
- **objective** : id, team_id, title, description, target_date (nullable), rag_status (`green` | `amber` | `red`), weight (int, défaut 1), is_active.
- **deliverable** : id, team_id, title, due_date, status (`done` | `on_track` | `at_risk` | `late`), linked_objective_id (nullable).
- **kpi** : id, team_id, name, unit (nullable), target_value (nullable, numeric), current_value (nullable, numeric), trend_status (`on_target` | `under_pressure` | `missed`), comment (nullable). → **Le statut de tendance est obligatoire ; la valeur chiffrée et la cible sont optionnelles** (le statut peut suffire seul).
- **highlight** : id, team_id, content (texte court), kind (`fact` | `blocker` | `risk`), created_at. → Contrainte applicative : **max 3 highlights actifs par équipe par cycle**, chacun ≤ 280 caractères, pour éviter les pavés.
- **report_snapshot** : id, team_id, submitted_by_user_id, submitted_at, payload (jsonb : copie figée des objectifs/livrables/kpi/highlights au moment de la soumission), cycle_label. → Sert l'**historisation** : chaque soumission d'un responsable crée un snapshot immuable.
- **audit_log** : id, user_id, action, entity, entity_id, timestamp, detail (jsonb).

Calcul du **statut dominant d'une équipe** (côté serveur, exposé par l'API, jamais recalculé côté client de façon divergente) :
- `red/bloqué` si ≥1 objectif rouge OU ≥1 KPI `missed` OU ≥1 livrable `late` OU ≥2 objectifs amber.
- sinon `amber/sous tension` si ≥1 objectif amber OU ≥1 KPI `under_pressure` OU ≥1 livrable `at_risk`.
- sinon `green/tenu`.
La donnée est marquée **périmée** si `now - dernier report_snapshot.submitted_at > seuil` (défaut 7j, configurable par variable d'env), indépendamment du statut RAG.

## 3. Stack technique

Choisir **la stack la plus simple qui tient la spec**. Recommandation par défaut (à suivre sauf raison forte) :

- Backend : **Python 3.12 + FastAPI + SQLAlchemy + Alembic** (migrations).
- Front : **React + Vite + TypeScript**, build statique servi par le backend OU par un service nginx du compose. Pas de framework lourd inutile. Tailwind autorisé.
- DB : **PostgreSQL 16** dans le `docker-compose`.
- Le tout orchestré par **un seul `docker compose up -d`**.

Si tu choisis une autre stack, elle doit rester mono-commande et entièrement dockerisée.

## 4. Authentification & contrôle d'accès

Trois mécanismes, par ordre de priorité d'implémentation :

1. **Breaking-glass (compte local de secours) — OBLIGATOIRE et fonctionnel dès le premier démarrage.**
   - Un compte admin local créé automatiquement au bootstrap, identifiants via variables d'env (`BREAKGLASS_EMAIL`, `BREAKGLASS_PASSWORD`) avec des valeurs par défaut documentées (`admin@local` / mot de passe aléatoire imprimé dans les logs au premier boot si non fourni).
   - Login par formulaire local, mot de passe hashé (argon2 ou bcrypt).
   - Toute connexion breaking-glass est tracée dans `audit_log`.

2. **OIDC — configurable, et fonctionnel si configuré.**
   - Variables d'env : `OIDC_ENABLED`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, `OIDC_SCOPES`.
   - Flux Authorization Code + PKCE. Mapping du `sub` / `email` vers `user`. Provisioning à la volée (création de l'utilisateur au premier login, rôle `viewer` par défaut, promu par un admin).
   - Si `OIDC_ENABLED=false`, le bouton OIDC est masqué et l'app reste pleinement utilisable en breaking-glass.

3. **SAML 2.0 (cible : PingFederate) — module activable par configuration.**
   - Variables d'env : `SAML_ENABLED`, `SAML_IDP_METADATA_URL` (ou chemin vers metadata XML), `SAML_SP_ENTITY_ID`, `SAML_ACS_URL`, certificats SP.
   - Implémentation complète du flux SP-initiated (utiliser une lib éprouvée, p.ex. `python3-saml`).
   - **Par défaut `SAML_ENABLED=false`** pour que l'app démarre sans métadonnées IdP réelles. Fournir un `README` clair pour brancher PingFederate (entity ID, ACS URL, attributs attendus : email, displayName, groupes).

**Modèle de rôles :**
- `admin` : gère équipes, utilisateurs, rôles, seuils ; accès total.
- `lead` (responsable d'équipe) : saisit/édite uniquement SON/SES équipe(s) ; soumet les cycles.
- `viewer` (dont le N+1) : **lecture seule** sur tout, accès au dashboard, aux drill-downs, aux exports et à l'historique.

## 5. Fonctionnalités (périmètre complet — tout est à livrer)

### 5.1 Dashboard de consolidation (écran d'accueil)
- 1 ligne par équipe, triable **par risque** (défaut, le pire en haut) et **par fraîcheur**.
- Pastille + bande de couleur = statut dominant calculé serveur.
- Compteurs synthétiques en haut : nb équipes, objectifs en rouge (total), échéances dépassées, équipes à donnée périmée.
- Par ligne : nom équipe, niveau (N-1/N-2) + responsable, statut + (n rouge / n amber / n objectifs), 1 highlight saillant, fraîcheur de la donnée, badge échéances dépassées.
- Filtres : par niveau hiérarchique, par statut, par fraîcheur.

### 5.2 Drill-down équipe
- Détail complet d'une équipe : tous les objectifs (avec RAG), livrables (avec échéances + statut), KPI (statut tendance + valeur/cible si saisies), highlights.
- Timeline des `report_snapshot` (historique des cycles) avec possibilité de comparer le cycle courant au précédent.

### 5.3 Saisie (responsable d'équipe)
- Formulaire structuré : édition des objectifs (RAG), livrables (statut + échéance), KPI (statut obligatoire + valeur/cible optionnelles), highlights (≤3, contraints).
- Bouton **« Soumettre le cycle »** → crée un `report_snapshot` immuable et met à jour la fraîcheur.
- Indication visuelle du temps écoulé depuis la dernière soumission.

### 5.4 Administration
- CRUD équipes (avec hiérarchie parent/enfant), affectation des responsables.
- CRUD utilisateurs, gestion des rôles.
- Réglage des seuils (fraîcheur, etc.).
- Consultation de l'`audit_log`.

### 5.5 Organigramme N-1/N-2
- Vue visuelle de la hiérarchie des équipes (arbre ou colonnes par niveau), chaque nœud affichant le statut dominant de l'équipe (vue « org + santé » combinée). Clic sur un nœud → drill-down.

### 5.6 Export / rapport
- **Export du dashboard et d'un rapport par équipe au format imprimable (PDF via rendu print CSS, ou génération PDF serveur).** Mise en page propre, un format identique pour toutes les équipes (le N+1 veut un format unifié).
- Export CSV des données brutes (objectifs/livrables/kpi) pour réutilisation.

### 5.7 Données de démonstration
- Au premier démarrage, **seed automatique** d'un jeu de données réaliste : ~9 équipes avec niveaux N-1/N-2, objectifs/livrables/KPI/highlights variés, et des fraîcheurs variées (dont 1-2 équipes en donnée périmée) pour que le dashboard soit immédiatement parlant. Le seed est idempotent et désactivable via `SEED_DEMO=false`.

## 6. Qualité UI

- Interface sobre et professionnelle, lisible, responsive (desktop prioritaire).
- Palette de statut cohérente : vert = tenu, orange = sous tension, rouge = raté/bloqué.
- La fraîcheur doit être visuellement distincte du statut RAG (ne pas confondre « vert mais vieux » avec « vert et frais »).
- Sentence case, pas d'ALL CAPS criards, pas d'emoji.
- i18n légère : libellés en **français** par défaut (le commanditaire est francophone).

## 7. API

- API REST documentée (OpenAPI/Swagger auto-exposé sur `/docs`).
- Endpoints couvrant : auth (breaking-glass/OIDC/SAML callbacks), teams, objectives, deliverables, kpis, highlights, snapshots, dashboard (agrégat consolidé), org-tree, exports, admin/users, audit-log.
- Le statut dominant et la fraîcheur sont **calculés et renvoyés par le serveur**.

## 8. Livrables attendus dans le dépôt

- Code source backend + frontend.
- `docker-compose.yml` (services : `app`/`api`, `web` si séparé, `db` Postgres ; volumes persistants pour la DB).
- `Dockerfile`(s) multi-stage propres.
- Migrations Alembic (ou équivalent) appliquées automatiquement au démarrage (entrypoint qui attend la DB, lance les migrations, puis le seed).
- `.env.example` exhaustif et commenté (toutes les variables des sections 3-4-5).
- `README.md` : démarrage en une commande, matrice des variables d'env, procédure de branchement OIDC et SAML/PingFederate, comptes de démo.
- `DECISIONS.md` : journal des choix tranchés en autonomie.
- Tests : au minimum tests d'API sur le calcul du statut dominant, la fraîcheur, la création de snapshot, et le contrôle d'accès par rôle. Les tests doivent passer.

## 9. Critères d'acceptation (tu les vérifies toi-même avant de t'arrêter)

1. Sur une machine vierge : `cp .env.example .env` puis `docker compose up -d --build` → tous les services montent, la DB migre, le seed s'applique.
2. `http://localhost:8080` affiche le dashboard peuplé par le seed, le pire en haut, les fraîcheurs visibles dont au moins une équipe « périmée ».
3. Login breaking-glass fonctionne (identifiants du `.env`).
4. Un `lead` ne peut éditer que son équipe ; un `viewer` est en lecture seule ; un `admin` a tout. Vérifié par test.
5. Soumettre un cycle crée un snapshot immuable, et le drill-down montre l'historique + comparaison cycle précédent.
6. L'organigramme affiche la hiérarchie avec le statut de chaque équipe et le clic mène au drill-down.
7. L'export PDF/imprimable produit un rapport propre et de format identique pour chaque équipe.
8. `OIDC_ENABLED=true` avec un issuer valide active le login OIDC sans casser le reste ; `SAML_ENABLED=true` câble le flux SAML. Avec les deux à `false`, l'app reste pleinement fonctionnelle en breaking-glass.
9. `/docs` expose l'API. Les tests passent (`docker compose run ... pytest` ou équivalent renvoie vert).
10. Aucun TODO, aucun placeholder « à implémenter », aucune fonctionnalité de la section 5 manquante.

## 10. Rappel final

Produit **complet, fini, dockerisé, démarrable en une commande, sans aucune intervention manuelle ni question posée**. Tu itères jusqu'au vert sur les 10 critères ci-dessus, puis tu t'arrêtes en résumant ce qui a été livré et comment le lancer.
