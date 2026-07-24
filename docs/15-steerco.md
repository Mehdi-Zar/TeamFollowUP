# 15 - Steerco (comite de pilotage) : saisie mensuelle et one-pager

Le module **Steerco** produit, pour le comite de pilotage, un **one-pager KPI par
squad** (HTML / PPTX) construit automatiquement a partir d'instantanes mensuels.
Chaque squad saisit des **valeurs brutes** ; tout le reste (variation vs M-1,
couleurs SLA, graphiques de l'annee) est **calcule au rendu**, jamais tape a la main.

Module optionnel, **desactive par defaut** : Administration -> Modules -> `steerco`.

## 1. Le modele : un instantane par mois

Une squad active le Steerco elle-meme (`squads.steerco_enabled`, en libre-service
depuis la Saisie ou Mes Squads). Elle depose ensuite **un instantane par mois**
(table `steerco_entries`, unique sur `(squad_id, period)`, `period` au format
`AAAA-MM`).

Un instantane contient uniquement les chiffres du mois :

```json
{"kpis": [{"label": "Cloud Users", "value": "247"}],
 "sla": {"services": ["Incidents", "Gitlab"], "cells": [{"v": "99,4%"}]},
 "incidents": "13",
 "last_events": [{"date": "12/07", "tag": "Incident", "text": "...", "sev": "amber"}],
 "next_events": []}
```

Le one-pager **n'est pas stocke** : il est reconstruit a la demande a partir des
instantanes de l'**annee** du rapport. C'est ce qui garantit la coherence :

| Element du one-pager | Origine |
|---|---|
| Cartes KPI (valeur) | l'instantane du mois demande |
| Variation vs M-1 (fleche + delta) | calculee entre le mois et M-1 (janvier se compare a decembre de l'annee precedente) |
| Ligne SLA "mois en cours" | l'instantane du mois demande |
| Ligne SLA "moyenne annuelle" | moyenne des mois renseignes de l'annee |
| Couleur d'une cellule SLA | calculee de la valeur : au-dessus de 90 % vert, de 80 a 90 % orange, en dessous de 80 % rouge |
| Graphes KPI et incidents | serie de janvier a decembre de l'annee (KPI indexes base 100) |
| Evenements (derniers / prochains) | l'instantane du mois demande ; la gravite colore la pastille de type |

> **Fenetre = annee civile.** Partout (graphes, grille de rattrapage, colonnes de
> l'assistant, colonnes du fichier Excel) la fenetre est la meme : les 12 mois de
> l'annee du rapport, de **janvier a decembre**. Les graphiques commencent donc
> toujours en janvier, et les mois qu'on saisit sont exactement ceux qu'on voit
> tracer. La definition unique est `year_months()` dans
> `backend/app/routers/steerco.py`.

## 2. Saisir (squad leader)

**Saisie -> carte Steerco**. La carte rappelle la cadence (mensuelle, alors que le
reporting au-dessus est hebdomadaire) et indique si le mois en cours est deja
rempli, quand et par qui.

Le bouton ouvre un **assistant en 5 etapes** : le mois, les KPI, SLA et incidents,
les evenements, puis un recapitulatif avec **apercu en direct du one-pager** (rien
n'est enregistre avant l'envoi). Les tableaux affichent les 12 mois de l'annee
(janvier a decembre) en lecture seule, la colonne du mois en cours etant surlignee
et modifiable.

A la premiere utilisation, le repli **"Importer l'historique de l'annee"** ouvre une
grille qui accepte un **coller depuis Excel** (une ligne par mois, de janvier a
decembre) pour amorcer les graphes en une fois.

## 3. Consulter et exporter (leadership)

**Dashboard -> onglet Steerco** (admins et tribe leaders) : choisir un mois et une
squad (ou toutes), l'apercu s'affiche dans la page. Le menu d'export de la page
propose le **HTML** et le **PPTX** (une diapositive 16:9 par squad). Les documents
sont rendus dans la langue de l'interface (anglais par defaut).

## 4. Import Excel (admin)

Alternative a la saisie en ligne, pour collecter les donnees hors application :
**Administration -> Import -> Importer des donnees Steerco**.

1. **Choisir la squad**, puis **telecharger son fichier**. Le classeur est genere
   **pour cette squad** : nom pre-rempli, mois courant, et surtout **les lignes KPI et
   SLA qu'elle suit reellement** (lues dans son dernier instantane). Sans squad
   choisie, on obtient la structure standard.
2. Remplir, puis **deposer** le fichier. Un resume s'affiche (squad, mois, nombre
   de mois / KPI / services SLA / evenements).

Le classeur a 7 onglets : Instructions, Infos, KPIs, SLA, Incidents,
Evenements passes, Evenements a venir.

- **Infos** : nom **exact** de la squad dans l'application (pre-rempli), mois du
  rapport (`AAAA-MM`), et les 3 sous-metriques Software Factory du mois en cours.
- **KPIs / SLA / Incidents** : 12 colonnes = les mois de l'annee, de janvier a
  decembre. Le mois du rapport est marque d'une `*`.
- **Evenements** : Date, Type, Libelle, Gravite (Critique / Attention / OK / Prevu).

Rien a saisir pour les variations ni les couleurs : elles sont recalculees au rendu.
Les valeurs SLA sont des pourcentages plafonnes a 100 (le fichier le controle, et
l'import le replafonne).

### Regle de fusion : l'import ajoute et met a jour, il ne supprime jamais

C'est la garantie qui rend le fichier et la saisie en ligne coherents. Le classeur
n'a pas besoin d'etre la photo complete du mois :

| Dans le fichier | Effet |
|---|---|
| Une ligne KPI / SLA connue, avec une valeur | la valeur du mois est mise a jour |
| Une ligne KPI / SLA connue, **case vide** | la valeur deja saisie dans l'app est **conservee** |
| Une **ligne ajoutee a la main** avec une valeur | le KPI / service est **ajoute** a la squad |
| Un KPI / service **absent du fichier** | **conserve**, et signale dans le resume d'import |
| Onglet evenements **vide** | les evenements saisis dans l'app sont **conserves** |

Pour **retirer** un KPI ou un service, on le supprime dans l'application (un clic
dans l'assistant). Le fichier ne peut donc jamais effacer par omission des donnees
qu'il ignorait.

L'import est **idempotent** par `(squad, mois)` : reimporter n'introduit pas de
doublon. Il **active** le Steerco sur la squad. Il echoue en `400` si la squad est
introuvable, si plusieurs squads portent ce nom, ou si le mois du rapport n'est pas
au format `AAAA-MM`.

> Les colonnes sont l'annee civile : changer le mois du rapport dans la meme annee
> ne decale pas les colonnes, cela deplace seulement l'asterisque du mois en cours.

### API directe (curl / CI)

```bash
# 1) recuperer le modele (mois courant ; ?squad_id= pour le fichier d'une squad)
curl -sk -b cookies.txt "https://<host>/api/admin/import-steerco/template?squad_id=3" -o steerco.xlsx

# 2) importer le fichier rempli
curl -sk -b cookies.txt -F "file=@steerco.xlsx" https://<host>/api/admin/import-steerco
```

## 5. Droits

| Action | Qui |
|---|---|
| Activer / desactiver le Steerco d'une squad | admin, tribe leader, le squad leader concerne |
| Saisir un instantane, rattraper l'historique, voir l'apercu | idem (writer + droit d'edition sur la squad) |
| Lire la consolidation et les documents (`/entries`, `onepager.html`, `document.*`) | admin, tribe leader (dans leur perimetre) |
| Telecharger le modele et importer un fichier | admin |

Toute ecriture est **auditee** (`steerco.enabled`, `steerco.upsert`,
`steerco.history`, `steerco.import`).

## 6. Ou est le code

| Role | Fichier |
|---|---|
| API, agregation annuelle, rendu HTML et PPTX | `backend/app/routers/steerco.py` |
| Modele et gabarit Excel, parsing, import | `backend/app/steerco_import.py` |
| Table `steerco_entries` + `squads.steerco_enabled` | `backend/alembic/versions/0027_steerco_entries.py` |
| Types et calculs partages (front) | `frontend/src/steerco.ts` |
| Assistant de saisie / grille de rattrapage / onglet consolidation | `frontend/src/components/Steerco{Wizard,Editor,Consolidation}.tsx` |
| Tests | `backend/tests/test_steerco.py` |
| Maquette d'origine du one-pager (reference visuelle, non maintenue) | `docs/assets/kpi-onepager.reference.html` |
