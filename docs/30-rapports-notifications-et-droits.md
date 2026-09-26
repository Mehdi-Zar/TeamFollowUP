# 30 - Rapports planifies, mails de modification et droits d'administration

Ce document decrit qui recoit quel document, quand, et qui peut le regler.

## 1. Le rapport planifie, par portee

Il existe deux sortes de planning, de meme forme :

- celui de l'**administrateur**, qui couvre toutes les tribes
  (`app_settings['weekly_report']`) ;
- celui de **chaque tribe**, regle par son tribe leader dans Administration >
  Rapport hebdomadaire (`app_settings['weekly_report:tribe:<id>']`). Le serveur
  epingle le tribe leader sur sa tribe : il ne lit ni n'ecrit le planning global,
  et les squads qu'il coche hors de sa tribe sont ignorees.

Le planificateur envoie celui de l'admin, puis celui de chaque tribe
(`report.send_due_weekly_reports`). Chaque planning garde son propre
`last_sent_day` et ses propres references « quoi de neuf » : l'un ne consomme pas
les nouveautes de l'autre.

## 2. Ce que recoivent les destinataires

Quatre options, cumulables :

| Option | Effet |
|---|---|
| `global_doc` | le document complet de la portee, en un seul mail (le comportement historique) |
| `per_squad` | un mail par squad, avec le document de cette squad seulement |
| `squad_leaders` | chaque squad leader, co-leaders compris, recoit le document de sa squad |
| `tribe_leader_digest` | planning admin seulement : chaque tribe leader recoit sa tribe, ses squad leaders en copie |

`squad_ids` choisit les squads des envois par squad (vide = toutes celles de la
portee). Le bouton **Envoyer maintenant a chaque squad leader** envoie tout de
suite, a chaque leader, le document de sa seule squad
(`POST /api/admin/report-config/send-squad-leaders`). Le meme envoi existe pour
une squad depuis sa page (**Envoyer au squad leader**), pour l'admin et le tribe
leader de la squad.

## 3. Le mail a chaque modification

Il part a chaque modification d'une squad et commence par une phrase qui dit qui a
modifie quoi et quand (« Alice a modifie : KPI, squad X, le ... »), suivie du
document de la squad. Les declencheurs couvrent l'avancement, la roadmap, les OTD,
le budget, les messages cles, et desormais les engagements de la squad, les KPI,
les comites, l'equipe et le moral. Une configuration enregistree avec tous les
anciens declencheurs coches recoit les nouveaux : « tout » veut toujours dire tout.

En plus de la liste d'adresses, deux boutons ajoutent a la liste le tribe leader de la squad et
ses squad leaders. Ce reglage reste celui de l'administrateur (une seule liste pour
toute l'application).

## 4. Qui voit quoi : un seul tableau

Administration > Personas et droits tient en **un seul tableau** : une ligne par
option, une colonne par persona. Les lignes suivent les menus : les sections de
l'application, puis les quatre familles de l'administration (organisation, services
et apparence, connexion et email, exploitation).

**Tout se choisit**, y compris les onglets jusqu'ici reserves a l'administrateur
(SMTP, SSO, sauvegardes, journaux...). Seule la colonne de l'administrateur est
verrouillee, pour que l'application ne perde jamais l'acces a ses reglages. Par
defaut, le tribe leader a ma tribe, plateformes, comptes, conges et rapport
hebdomadaire ; les autres personas n'ont aucun onglet.

Le serveur suit les cases (`app/tabaccess.py`) :

- un onglet **global** coche ouvre ses routes a ce persona. `deps.require_admin`
  retrouve l'onglet d'une route par son chemin (`ROUTE_TABS`) ; une route qu'aucun
  onglet ne couvre reste reservee a l'administrateur ;
- un onglet **de tribe** (ma tribe, comptes, conges, plateformes, rapport
  hebdomadaire) fait agir ce persona comme le tribe leader de sa propre tribe
  (`acting_manager`) ; sans tribe, il n'a rien ;
- l'onglet Moderation permet de moderer les messages du fil qu'on voit ;
- **« Voir en tant que »** n'est pas un onglet et reste a l'administrateur : c'est
  tous les droits a la fois (`deps.require_strict_admin`).

Le menu Administration apparait des qu'un persona a au moins un onglet.

## 5. Deux regles de saisie liees

- **Deux engagements OTD au plus par mois** : par tribe pour ceux du management,
  par squad pour ceux d'une squad (`otds.MAX_OTD_PER_MONTH`). Un troisieme, ou un
  engagement deplace vers un mois plein, est refuse (409).
- **Un squad leader arrive sur sa squad** dans la saisie ; le selecteur n'apparait
  que s'il en dirige plusieurs.

## Ou est le code

| Role | Fichier |
|---|---|
| Plannings et options | `backend/app/reportconfig.py`, `backend/app/report.py` (`_send_schedule`) |
| Routes du rapport | `backend/app/routers/admin.py` (`/report-config`) |
| Mail de modification | `backend/app/changenotify.py`, `backend/app/changeconfig.py` |
| Onglets par persona | `backend/app/personasconfig.py`, `backend/app/tabaccess.py`, `backend/app/deps.py` |
| Ecrans | `frontend/src/pages/admin/configuration.tsx`, `frontend/src/pages/admin/organisation.tsx` |
| Tests | `backend/tests/test_report.py`, `test_changenotify.py`, `test_rbac_admin.py`, `test_otds.py` |
