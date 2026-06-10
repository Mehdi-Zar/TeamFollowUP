# REFONTE — Tribe Run Tracker v2 (orientée squads + roadmap trimestrielle)

Spécification consolidée à partir du Q&A. Sert de contrat pour la refonte.

## Ajustements v3 (personas, organigramme, membres, saisie guidée)

- **4 personas** : `admin` (tout + Administration/Réglages, seul), `tribe_leader` (crée/gère les
  squads, gère les membres, **pose les objectifs et leur statut**, édite l'organigramme global),
  `squad_leader` (gère SA squad : roadmap, KPIs, membres ; objectifs en lecture seule),
  `member` (lecture seule). Renommage v2→v3 : leader→squad_leader, viewer→member, + tribe_leader.
- **Aperçu persona** : l'admin bascule « Voir en tant que » pour prévisualiser l'UI de chaque
  rôle (aperçu visuel lecture seule, droits réels inchangés ; `effectiveRole` côté client).
- **Suppression des catégories** de squad (liste plate simple) et **suppression des points
  saillants** (highlights) — modèle, API, UI, seed, snapshot, tests.
- **Membres** : table `members` (fiche `full_name` + `role_title`, `user_id` optionnel pour relier
  un compte). Gérés par admin/tribe (toutes squads) et squad_leader (sa squad). Affichés en
  organigramme visuel dans le détail de la squad.
- **Organigramme global éditable (hybride)** : table `org_nodes` (arbre `parent_id`, `title`,
  `person_name`, `squad_id` optionnel → affiche le statut de la squad). CRUD réservé à
  admin/tribe ; lecture pour tous. À la suppression d'un nœud, ses enfants remontent au parent.
- **Objectifs** : édition réservée à admin/tribe_leader (le squad_leader les voit en lecture seule).
- **Saisie guidée** : page unique + bandeau explicatif + **checklist de complétion** + aides en
  ligne ; sections roadmap / KPIs / membres éditables, objectifs en lecture seule selon le rôle.
- **Dashboard plus aéré** : grandes cartes (minmax 360px) avec, en plus des 4 mini-barres et de la
  pastille, le détail objectifs R/A/V, jalons livrés/total, jalons en retard et nb de membres.

---

(Contrat v2 d'origine ci-dessous.)

## 1. Charte graphique — alignée sur RunAssessment

Migration de Tailwind vers la charte exacte de `C:\Claude\RunAssessment` :
- En-tête **dégradé navy** `linear-gradient(90deg,#141B47,#1E2761)`, texte blanc,
  onglets pills (inactif `#CADCFC`, actif blanc sur fond translucide).
- Police **Calibri, Carlito, "Segoe UI"**. Fond `#F5F7FA`. Conteneur centré max 1180px.
- **Tokens CSS** (`theme.css`) : `--navy #1E2761`, `--accent #175CD3`,
  `--green #027A48`, `--orange #B54708`, `--red #B42318`, cartes rayon 14px + ombre douce.
- Composants : `.card`, `.btn` / `.btn-secondary` / `.btn-ghost`, `.badge-green|orange|red|navy|grey`,
  `.kpi` (tuile), `.banner`, `.progress`, tables sobres. Pas d'emoji, sentence case.

## 2. Modèle de données (refonte)

- **squad** (ex-team, **liste plate**) : id, name, description, **category** (texte libre :
  « Cloud provider », « Service », « Data »…), leader_user_id, display_order.
  → Suppression de `parent_team_id`, `hierarchy_level`, `cadence`.
- **user** : inchangé (admin | leader | viewer ; break-glass ; OIDC/SAML subject).
  Rôle « lead » renommé **leader** côté libellés.
- **objective** (**annuel**) : id, squad_id, **year**, title, description, target_date?,
  rag_status (green|amber|red), weight, is_active. *Indépendant des jalons.*
- **roadmap_item / jalon** : id, squad_id, **year**, **quarter** (1-4), title, description?,
  **status** (`planned` | `in_progress` | `done` | `at_risk` | `late`), display_order.
  *Pas de date d'échéance obligatoire ; « en retard » et « à risque » sont saisis manuellement.*
- **quarter_progress** : id, squad_id, **year**, **quarter**, **progress_pct** (0-100, curseur
  saisi par le leader), comment?. Unicité (squad, year, quarter).
- **kpi** : inchangé (squad_id, name, unit?, target?, current?, trend_status, comment?). *Détail seulement.*
- **highlight** : inchangé (squad_id, content ≤280, kind, is_active ; max 3 actifs). *Détail seulement.*
- **report_snapshot** : inchangé ; payload = copie figée {objectives, jalons, quarter_progress,
  kpis, highlights} au moment de la soumission ; cycle_label.
- **app_setting**, **audit_log** : inchangés.

## 3. Règles de calcul (serveur)

- **Quarter courant** = dérivé de la date serveur (mois → Q ; ex. juin 2026 → 2026-Q2).
- **Pastille de statut d'une squad** (roadmap du quarter courant + objectifs combinés) :
  - **rouge** si ≥1 jalon du quarter courant `late`, OU ≥1 objectif (année courante) `red`,
    OU ≥2 objectifs `amber` ;
  - sinon **orange** si ≥1 jalon du quarter courant `at_risk`, OU ≥1 objectif `amber` ;
  - sinon **vert**.
  *Les KPIs n'entrent pas dans la pastille.*
- **Avancement d'un quarter** = `quarter_progress.progress_pct` (curseur du leader). Pas de calcul auto.
- **Fraîcheur** : « périmé » si `now - dernière soumission > seuil` (défaut 7j, configurable). Conservée.

## 4. Écrans

### 4.1 Accueil = dashboard « résumé de tous » (grille de cartes)
- Bandeau compteurs : nb squads, squads avec jalons en retard, total jalons de l'année, squads périmées.
- **Sélecteur d'année** (défaut = année courante). **Vue annuelle Q1→Q4 par défaut.**
- **1 carte par squad** : nom + catégorie + responsable, **pastille**, **4 mini-barres Q1→Q4**
  (avancement), nb jalons en retard sur l'année, badge de fraîcheur. Clic → détail squad.
- **Filtres** : catégorie, statut, fraîcheur.

### 4.2 Détail squad (drill-down, « voir plus »)
- Objectifs annuels (RAG), **roadmap par quarter** (jalons groupés Q1→Q4 avec statut),
  avancement (curseur) par quarter, **KPIs chiffrés**, **points saillants**,
  **historique des soumissions + comparaison**, **exports PDF/CSV**.

### 4.3 Saisie (leader)
- Édition objectifs (année), jalons (par quarter + statut), **curseur d'avancement** par quarter,
  KPIs, highlights (≤3). Bouton **« Soumettre »** → snapshot immuable + horodatage fraîcheur.

### 4.4 Organigramme / annuaire des squads
- Squads **groupées par catégorie**, chaque squad = nœud avec leader + pastille + fraîcheur ;
  clic → détail. (Remplace l'arbre N-1/N-2.)

### 4.5 Administration
- CRUD squads (nom, catégorie, responsable, ordre), CRUD utilisateurs & rôles,
  réglage du seuil de fraîcheur, journal d'audit.

## 5. Rôles
- **admin** : tout. **leader** : édite SA/SES squad(s), soumet. **viewer** (N+1) : lecture seule.

## 6. Conservé de la v1
- Auth breaking-glass + OIDC + SAML, `/docs` OpenAPI, migrations Alembic au démarrage,
  seed de démo idempotent (squads variées, catégories, jalons sur l'année, dont squads périmées),
  exports PDF (print-CSS) + CSV, tests (statut, fraîcheur, snapshot, RBAC, + avancement roadmap),
  `docker compose up -d` → http://localhost:8080.

## 7. Retiré de la v1
- Hiérarchie N-1/N-2 (`parent_team_id`, `hierarchy_level`), `cadence`,
  ancien objet « livrable » (remplacé par les jalons de roadmap), tri « par fraîcheur » du tableau
  (remplacé par la grille de cartes annuelle).
