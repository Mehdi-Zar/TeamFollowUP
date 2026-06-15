# DECISIONS.md — choix tranchés en autonomie

Journal des décisions prises sans validation, selon le principe « le plus simple
qui satisfait la spec ».

## Refonte v2 (squads + roadmap trimestrielle) — voir REFONTE_SPEC.md

- **Charte graphique reprise de RunAssessment** : abandon de Tailwind au profit d'un
  `theme.css` à tokens (navy `#1E2761`, accent `#175CD3`, Calibri), en-tête dégradé
  navy, cartes/badges/pills identiques. i18n laissée de côté (FR uniquement) pour ne
  pas alourdir le périmètre.
- **`team` → `squad` (liste plate)** : suppression de la hiérarchie N-1/N-2, de
  `cadence` et de l'objet « livrable » (remplacé par les jalons de roadmap). Ajout d'un
  champ libre `category` (filtrage + organigramme par catégorie).
- **Roadmap = jalons par quarter** : table `roadmap_items` (year + quarter + statut
  manuel). Pas de date d'échéance ; « en retard » / « à risque » sont des statuts saisis.
- **Avancement = curseur manuel** : table `quarter_progress` (squad, year, quarter,
  progress_pct), unicité (squad, year, quarter). Pas de calcul auto à partir des jalons.
- **Objectifs annuels** (champ `year`), indépendants des jalons (pas de lien formel).
- **Pastille de statut** = jalons du **quarter courant** (late→rouge, at_risk→orange)
  combinés aux objectifs de l'année (rouge, ou ≥2 orange). Les KPIs n'entrent pas dans
  la pastille (détail seulement). Pour une année autre que l'année courante, la pastille
  considère les jalons de toute l'année (`quarter=None`).
- **Dashboard = vue annuelle** : sélecteur d'année (défaut année courante), grille de
  cartes (4 mini-barres Q1→Q4 + pastille), tri « pire en haut » (risque puis retards).
- **Détail conservé** : KPIs, points saillants, historique + comparaison, exports — tout
  sous le drill-down d'une squad.
- **Rôle `lead` renommé `leader`** ; mécanisme de soumission (snapshot immuable +
  fraîcheur) conservé. Le snapshot fige objectifs + jalons + avancement + KPIs + highlights.

## v1 (historique)

## Architecture

- **Service unique `app` (FastAPI) servant à la fois l'API et le SPA React.**
  Plutôt qu'un service `web` nginx séparé. Cela réduit le nombre de conteneurs,
  supprime une couche de configuration et garantit que l'origine est identique
  pour le front et l'API (cookies de session sans CORS). Le compose comporte donc
  deux services : `app` et `db`. Critère « mono-commande » pleinement respecté.
- **Port hôte 8080 → conteneur 8000.** L'app écoute en 8000 dans le conteneur,
  exposée sur `http://localhost:8080`.
- **La base de données n'est pas exposée sur l'hôte.** Elle reste sur le réseau
  interne du compose (sécurité + évite les collisions de port 5432). Accès DB
  uniquement via le service `app`.

## Persistance & migrations

- **Colonnes `String` plutôt qu'`ENUM` PostgreSQL** pour les statuts (RAG, tendance,
  etc.). Les valeurs autorisées sont validées au niveau applicatif (Pydantic
  `Literal`). Cela évite la fragilité des migrations d'enum Postgres et garde le
  schéma portable (les tests tournent sur SQLite).
- **Migration Alembic initiale unique et écrite à la main** (`0001_initial`),
  appliquée automatiquement par l'entrypoint (`alembic upgrade head`) avant le seed.
- **Seuil de fraîcheur stocké en base** (`app_settings`) pour être modifiable à
  chaud par un admin, avec valeur par défaut issue de la variable d'env
  `STALENESS_THRESHOLD_DAYS`.

## Authentification

- **Sessions par JWT signé (HS256) en cookie httpOnly `trt_session`.** Simple,
  sans store de session externe.
- **Hachage Argon2** (`argon2-cffi`) pour les mots de passe locaux.
- **Compte de secours (breaking-glass)** créé/réconcilié à chaque démarrage par
  `app.bootstrap`. Si `BREAKGLASS_PASSWORD` est vide, un mot de passe aléatoire est
  généré et imprimé dans les logs.
- **OIDC via Authlib** (Authorization Code + PKCE), **SAML via python3-saml**
  (flux SP-initiated). Les deux sont importés paresseusement et désactivés par
  défaut : l'app démarre et fonctionne intégralement en breaking-glass sans eux.
- **Provisioning à la volée** pour OIDC/SAML : création de l'utilisateur au premier
  login avec le rôle `viewer`, promu ensuite par un admin.

## Export / rapport

- **PDF via rendu print-CSS** (pages `/print/...` + `window.print()`) plutôt que
  génération PDF serveur. C'est l'option explicitement autorisée par la spec, sans
  dépendance système lourde (pas de WeasyPrint/cairo/pango), et le format est
  unifié pour toutes les équipes. Export **CSV** servi par l'API (`/api/exports/...`).
- **Rapport hebdomadaire HTML + PPTX** (`app/report.py`, `/api/reports/weekly.*`) :
  document combiné *dashboard (état actuel) + revue hebdo (mouvements de la semaine)*.
  Le HTML est autonome (CSS inline) — sert à la fois au téléchargement, à l'aperçu
  navigateur et au corps d'email. Le **PPTX** est généré côté serveur avec
  `python-pptx` (pur Python, pas de LibreOffice) : slide titre + synthèse + points
  d'attention + une slide-table par tribu. Rendu dégradé en HTML seul si `python-pptx`
  absent (réponse 501 pour le téléchargement direct).
- **Envoi automatique hebdomadaire** piloté par le scheduler in-process de `main.py`
  (tick horaire), `report.send_due_weekly_reports` : idempotent à la semaine ISO
  (`last_sent_week`), déclenché le jour/heure configurés (`app_settings['weekly_report']`).
  Destinataires = **liste fixe configurable** (rapport global, côté admin) **+ opt-in
  par utilisateur** (`users.subscribe_weekly_report`, rapport limité à leur périmètre :
  global pour les admins, leur tribu pour les tribe leaders). Email = **HTML inline +
  PPTX en pièce jointe** (`mail.send_email(..., html=True)`). Nécessite un SMTP actif.

## Front-end

- **React + Vite + TypeScript + Tailwind**, build statique copié dans l'image
  backend (`app/static`) et servi par FastAPI avec fallback SPA sur `index.html`.
- **Type-check non bloquant pour le build Docker** : `vite build` (esbuild)
  transpile sans bloquer sur les types, pour fiabiliser la construction de l'image.
  `npm run typecheck` reste disponible.

## Règles métier

- **Statut dominant calculé côté serveur** (`app/status.py`), exposé par l'API,
  jamais recalculé de façon divergente côté client.
- **Seuil de fraîcheur** : une équipe est « périmée » si
  `now - dernière soumission > seuil`. À exactement le seuil, elle n'est pas encore
  périmée (`age_days > seuil`).
- **Snapshots immuables** : aucune route d'édition/suppression de `report_snapshot`.
  Le payload est une copie figée JSON au moment de la soumission.
- **Max 3 highlights actifs par équipe**, 280 caractères chacun, contrainte
  appliquée à la création et à la réactivation.
