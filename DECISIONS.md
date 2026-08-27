# DECISIONS.md - choix tranchés en autonomie

Journal des décisions prises sans validation, selon le principe « le plus simple
qui satisfait la spec ».

## Refonte v2 (squads + roadmap trimestrielle) - voir REFONTE_SPEC.md

- **Charte graphique maison** : abandon de Tailwind au profit d'un
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
- **Détail conservé** : KPIs, points saillants, historique + comparaison, exports - tout
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
- **Port unique, protocole selon `TLS_ENABLED`.** Le conteneur n'ouvre jamais qu'un
  seul port : **HTTP 8000** par défaut, le TLS étant terminé par l'infrastructure
  (Gateway API sur GKE, ALB, reverse proxy) - c'est le modèle recommandé ; ou
  **HTTPS 8443** avec `TLS_ENABLED=true`, l'app terminant le TLS elle-même
  (certificat auto-signé par défaut, remplaçable via l'admin) pour un déploiement
  autonome. Dans les deux cas la redirection HTTP→HTTPS est déléguée à
  l'infrastructure : l'app n'a pas de listener dédié.
  *(Historique : v1 = hôte 8080 → conteneur 8000 ; v2 = 8443 HTTPS + 8080 redirigeant
  en 301, listener retiré ; v3 = les deux modes ci-dessus, HTTP simple par défaut.)*
- **Une seule URL publique, les URL SSO en dérivent.** Le port d'écoute ne dit rien
  de l'adresse vue par le navigateur : derrière une Gateway, le pod écoute en HTTP
  8000 alors que les utilisateurs tapent `https://…` sur 443. Plutôt que de faire
  saisir trois URL absolues (redirection OIDC, entity ID et ACS SAML) qu'il faudrait
  maintenir cohérentes à la main, on ne configure que l'**URL publique**
  (`PUBLIC_BASE_URL`, ou le champ dédié dans Administration → Authentification) et
  les trois sont construites par concaténation d'un chemin fixe. Laissée vide, elle
  est déduite de la requête (`X-Forwarded-Proto` / `-Host`), ce qui rend le
  développement local et tout déploiement mono-hôte configuration-free. Un forçage
  par URL reste possible pour les enregistrements IdP existants, mais un forçage qui
  ne fait que répéter la valeur dérivée est ramené à vide à l'enregistrement, pour
  qu'il continue de suivre l'URL publique au lieu de figer un hôte périmé.
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
  Le HTML est autonome (CSS inline) - sert à la fois au téléchargement, à l'aperçu
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

## Dette laissee ouverte, et pourquoi (2026-08-27)

Trois points du registre de dette ont ete examines puis **volontairement laisses
en l'etat**. Les fermer aurait coute plus que ce qu'ils rapportent, et le dire est
plus utile que de les traiter a moitie.

- **TD-UI-1, tokeniser les espacements et la typographie.** `theme.css` a deja des
  tokens de couleur ; ce qui manque, ce sont les espacements, ecrits en dur dans
  des centaines de `style={{ gap: 8, marginTop: 12 }}`. Introduire l'echelle est
  trivial ; migrer les appelants ne l'est pas, et rien ici ne permet de detecter
  une regression visuelle (aucune comparaison de captures). Ajouter des tokens que
  personne n'utilise serait du CSS mort. **Decision** : ne rien changer tant qu'il
  n'y a pas de refonte visuelle qui justifie la migration, ou un test de regression
  visuelle qui la rende verifiable.

- **TD-DATA-1, une table `personas` avec cle etrangere.** `users.role` est une
  chaine libre et les personas vivent dans `app_settings`. L'integrite est deja
  assuree autrement : supprimer un persona **reassigne** ses utilisateurs vers
  `member` (`routers/admin.py`, teste par
  `test_deleting_persona_reassigns_users_to_member`), et un role inconnu ne donne
  **aucune** capacite (`persona_caps`, fail-closed). Passer a une table demanderait
  une migration touchant l'authentification, le RBAC, les seeds et les tests, pour
  une garantie que le code fournit deja. **Decision** : garder le modele actuel ;
  ce n'est un sujet que le jour ou les personas doivent porter autre chose que des
  capacites.

- **La chaine de deploiement automatisee (dev vers staging vers prod).** Un
  workflow de deploiement ne se verifie qu'en deployant : sans environnement de
  destination ni identifiants, on ne peut qu'ecrire du YAML plausible et esperer.
  Livrer une automatisation jamais executee est pire que la procedure manuelle,
  qui, elle, est ecrite et a ete suivie ([docs/13](docs/13-maintenance-and-updates.md)).
  **Decision** : ne pas livrer de pipeline non teste. Les options et leurs
  compromis sont deja decrits dans `docs/13`, a trancher avec la plateforme cible.
