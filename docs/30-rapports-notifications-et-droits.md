# 30 - Rapports planifies, mails de modification et droits d'administration

Ce document decrit qui recoit quel document, quand, et qui peut le regler.

## 1. Le menu « Rapports par mail », reserve a l'admin

Les rapports envoyes par mail se reglent dans **Administration > Rapports par
mail**, par l'administrateur seul (l'onglet `report` est reserve a l'admin,
comme l'authentification ou l'annuaire). Il n'y a plus d'abonnement personnel :
personne ne regle ce qu'il recoit lui-meme. Trois onglets :

| Onglet | Ce qu'il regle |
|---|---|
| Tribes | le rapport programme d'une tribe (l'admin choisit la tribe) |
| Direction | le document complet, toutes les tribes, a des adresses fixes |
| A chaque modification | les avis de modification (section 3) |

Deux sortes de planning, chacun avec son calendrier (jours, heure de Paris),
l'option « seulement s'il y a du nouveau » et son `last_sent_day` : la Direction
(`app_settings['weekly_report']`) et chaque tribe
(`app_settings['weekly_report:tribe:<id>']`).

## 2. Qui recoit quoi, pour une tribe

Le **tribe leader est le destinataire principal**. Il recoit au choix
(`leader_mode`) :

- `tribe` : un mail avec le document de sa tribe ;
- `per_squad` : un mail par squad.

**Un seul mail, jamais deux pour une meme personne** : les responsables de
squad mis en copie rejoignent le mail du tribe leader. En mode `tribe`, ils sont
en copie du document de la tribe (ils voient donc toute la tribe) ; en mode
`per_squad`, du mail de leur squad.

| Ligne | Reglage | Ce qu'elles recoivent |
|---|---|---|
| Par role dans la squad | `copy_leader`, `copy_co_leaders`, `copy_contributors` | en copie du mail du tribe leader (voir ci-dessus) |
| Par persona | `copies[]` type `persona` | les personnes de la tribe qui ont cette persona |
| Par nom | `copies[]` type `user` | une personne de la tribe |
| Par adresse | `copies[]` type `email` | une adresse libre |

Pour chaque copie par persona, nom ou adresse, on choisit ce qu'elle recoit : le
document de la tribe, ou les mails des squads (toutes, ou celles cochees). Ces
mails de squad existent aussi en mode `tribe`, pour ces seules copies.
`squad_ids` limite les squads concernees (vide = toutes).

### Ce que contient chaque mail

Le corps du mail est toujours le resume du rapport. Les **pieces jointes** se
choisissent par sorte de mail (`docs`) : le mail de la tribe (`tribe`), les
mails de squad (`squad`) et celui de la Direction (`all`). Quatre documents,
joints en PowerPoint et mis en page par le Studio des exports :

| Cle | Document |
|---|---|
| `weekly` | Rapport hebdomadaire |
| `dashboard` | Tableau de bord |
| `roadmap` | Roadmap |
| `dependencies` | Dependances |

Aucun document coche : le mail ne porte que le resume. Par defaut, chaque sorte de
mail joint le rapport hebdomadaire.

### Les regles du plan (`app/mailplan.py`)

- un mail sans personne en « A » passe ses copies en « A » ;
- une adresse ne figure qu'une fois par mail ;
- les personnes nommees sans adresse sont listees a l'ecran ;
- « seulement s'il y a du nouveau » se decide **mail par mail** : chaque document
  a sa propre reference, une squad qui n'a pas bouge ne declenche rien.

### L'ecran

La liste des destinataires, mail par mail, avec les pieces jointes de chacun, est
**recalculee a chaque modification, avant d'enregistrer**
(`POST /api/admin/report-config/plan` avec les reglages en cours, sans rien
ecrire). Chaque ligne du reglage montre ses destinataires et son **apercu**
(`POST /preview`, lui aussi sur les reglages en cours). Un vrai mail part des
reglages enregistres : **m'envoyer un test** (`/test`, a l'adresse de l'admin) et
**envoyer maintenant** (`/send-now`, hors calendrier, sans toucher aux references
« quoi de neuf »). Le bouton **Envoyer au squad leader** de la page d'une squad
reste, pour l'admin (`/send-squad-leaders`).

Les reglages de l'ancienne forme (`global_doc`, `per_squad`, `squad_leaders`,
`tribe_leader_digest`, `attach_pptx`) sont convertis une fois
(`reportconfig.ensure_v2`) : la liste fixe de l'admin devient la Direction ; « chaque
squad leader recoit sa squad » et le recapitulatif par tribe deviennent, pour
chaque tribe, un planning au meme calendrier, tribe leader destinataire et squad
leaders (co-leaders compris) en copie ; la liste fixe d'une tribe devient des
copies par adresse ; « PPTX joint » decoche devient « aucun document ». La table
des anciens abonnements personnels reste en base mais n'est plus lue.

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

- **Deux engagements OTD au plus par mois pour une meme squad**, qu'elle les prenne ou
  que le management les lui assigne (`otds.MAX_OTD_PER_MONTH`). Un troisieme, ou un
  engagement deplace vers un mois plein, est refuse (409). Le plafond etait par tribe
  pour le management, ce qui limitait toute une tribe a deux engagements par mois. Un
  engagement du management qui ne vise aucune squad n'est pas plafonne.
- **Un squad leader arrive sur sa squad** dans la saisie ; le selecteur n'apparait
  que s'il en dirige plusieurs.

## Ou est le code

| Role | Fichier |
|---|---|
| Plannings et options | `backend/app/reportconfig.py`, `backend/app/mailplan.py` (qui recoit quoi), `backend/app/report.py` (`_send_schedule`, `send_plan_now`, `plan_preview`) |
| Routes du rapport | `backend/app/routers/admin.py` (`/report-config`) |
| Mail de modification | `backend/app/changenotify.py`, `backend/app/changeconfig.py` |
| Onglets par persona | `backend/app/personasconfig.py`, `backend/app/tabaccess.py`, `backend/app/deps.py` |
| Ecrans | `frontend/src/components/ReportsMail.tsx` (menu Rapports par mail), `frontend/src/pages/admin/configuration.tsx`, `frontend/src/pages/admin/organisation.tsx` |
| Tests | `backend/tests/test_mail_plan.py`, `test_report.py`, `test_changenotify.py`, `test_rbac_admin.py`, `test_otds.py` |
