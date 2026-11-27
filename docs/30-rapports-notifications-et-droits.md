# 30 - Rapports planifies, mails de modification et droits d'administration

Ce document decrit qui recoit quel document, quand, et qui peut le regler.

## 1. Le menu « Rapports par mail » : des diffusions

Les rapports envoyes par mail se reglent dans **Administration > Rapports par
mail**. Il n'y a plus d'abonnement personnel : personne ne regle ce qu'il recoit
lui-meme. Deux onglets :

| Onglet | Ce qu'il regle | Qui |
|---|---|---|
| Rapports planifies | les **diffusions** : une carte par envoi programme | l'admin (toutes), le tribe leader (celles de sa tribe) |
| Alertes de modification | les avis de modification (section 3) | l'admin |

Une **diffusion** est un envoi programme : un perimetre (une tribe, ou la
Direction), un calendrier (jours, heure et minutes de Paris, par 5 minutes,
reglees avec des boutons - et +), l'option « seulement s'il y a
du nouveau », ses destinataires et ses pieces jointes. Il peut y en avoir
**plusieurs par tribe** (les leaders le lundi, un comite le vendredi). Chacune est
rangee dans `app_settings['report_diffusion:<id>']` avec son `last_sent_day`
(`app/reportconfig.py`).

L'onglet `report` peut maintenant etre donne a une persona (Administration >
Personas et droits) : elle regle alors les diffusions de **sa** tribe, comme un
tribe leader. Il est coche par defaut pour le tribe leader. La Direction et les
alertes de modification restent a l'admin. Routes : `/api/admin/diffusions`
(`app/routers/diffusions.py`).

### La carte

Chaque carte dit tout d'un coup d'oeil : nom, perimetre, interrupteur
**Active / En pause**, jours et heure, pieces jointes, « A » et « Cc » (les
premiers noms puis « et N autres »), nombre de mails, personnes sans adresse,
**prochain envoi** et **dernier envoi** (point vert ou rouge, clic = historique).
Boutons : Editer, Apercu, M'envoyer un test, Envoyer maintenant (deuxieme clic de
confirmation), Supprimer (idem).

### La fenetre d'edition

Un **pas a pas**, une etape a la fois (Precedent / Suivant), avec le menu des
etapes a gauche et ce que chacune contient deja : 1. pour quelle tribe (« Toutes
les tribes » = la Direction, document complet) et le nom, facultatif ; 2. quand ;
3. qui recoit ; 4. contenu du mail ; 5. pieces jointes. « + Nouvelle diffusion » ouvre directement
l'etape 1. Une diffusion enregistree garde sa tribe et peut etre enregistree a
n'importe quelle etape. A droite, toujours visibles, **qui
recoit quoi** (un bloc par mail, cliquable) et l'**apercu du mail choisi**, tel
qu'il sera recu (objet, A, Cc, pieces jointes, corps). Les deux sont recalcules a
chaque clic, **avant d'enregistrer** (`POST /api/admin/diffusions/plan` et
`/preview` avec les reglages en cours, sans rien ecrire). Un vrai mail part des
reglages enregistres.

### L'historique

Chaque envoi est note dans la table `report_sends` : programme, envoye a la main
ou test, nombre de mails, destinataires, mails refuses et la raison donnee par le
serveur de mails. Quand le serveur refuse tout, le planificateur reessaie a chaque
heure (pas a chaque passage de 5 minutes), mais l'echec n'est note qu'une fois par
jour. Le planificateur passe toutes les 5 minutes pour les rapports par mail ; ses
autres taches (purge, sauvegarde automatique, rappels Steerco) restent horaires.
Un mail en retard (application arretee a l'heure prevue) part au passage suivant. Les 100 derniers envois de
chaque diffusion sont gardes ; supprimer la diffusion efface son historique.

## 2. Qui recoit quoi, pour une tribe

Le **tribe leader est le destinataire principal**. Il recoit, au choix et
**cumulables** :

- `leader_tribe` : le mail de toute la tribe ;
- `leader_squads` : un mail par squad.

Les gens de chaque squad, par role (`copy_leader`, `copy_co_leaders`,
`copy_contributors`) :

- quand le tribe leader recoit **seulement** le mail de la tribe, ils sont en
  copie de ce mail (un seul mail, ils voient toute la tribe, comme avant) ;
- sinon, chacun est sur le mail de **sa** squad (en copie quand le tribe leader
  le recoit aussi, en « A » sinon).

Les autres destinataires se nomment dans un seul champ (un nom, une persona ou
une adresse) :

| Type | Reglage | Ce qu'ils recoivent |
|---|---|---|
| Par persona | `copies[]` type `persona` | les personnes de la tribe qui ont cette persona |
| Par nom | `copies[]` type `user` | une personne de la tribe |
| Par adresse | `copies[]` type `email` | une adresse libre |

Pour chacun, on choisit ce qu'il recoit : le mail de la tribe, ou les mails des
squads (toutes, ou celles cochees). `squad_ids` limite les squads concernees
(vide = toutes).

Pour la **Direction**, les destinataires sont nommes de la meme facon (personne,
persona de toutes les tribes, adresse) et recoivent tous le document complet.

### Ce que contient chaque mail

Le **corps du mail** se compose, par sorte de mail (`body`), de blocs a cocher
(`reportconfig.BODY_SECTIONS`), dans cet ordre :

| Bloc | Contenu |
|---|---|
| `changes` | nouveautes depuis le dernier envoi |
| `kpis` | chiffres cles (pour une squad : statut, avancement, derniere saisie, squad leader) |
| `squads` | tableau des squads (pas pour le recap d'une squad) |
| `key_messages` | messages cles (risques, alertes, reussites) |
| `late_otds` | engagements (OTD) en retard |
| `kpi_watch` | KPI sous pression ou manques |
| `milestones` | jalons bloques ou a risque |

Dans le recap d'une tribe, chaque point d'attention commence par le nom de sa
squad. Quand tous les points d'attention coches sont vides, le mail le dit
(« Aucun point d'attention cette semaine »). L'etape « Contenu du mail » montre
**une seule liste** de blocs, numerotes dans l'ordre du mail, a cocher a la main ;
elle vaut pour tous les mails de la diffusion (le tableau des squads ne s'applique
pas au recap d'une squad, les chiffres cles y deviennent l'etat de la squad). Une
nouvelle diffusion a tous les blocs coches. Une diffusion enregistree avant ce
choix garde son contenu d'avant (`DEFAULT_BODY`).

Les **pieces jointes** se
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
- « seulement s'il y a du nouveau » se decide **mail par mail** : chaque mail a sa
  propre reference (`d<id>:...`, propre a la diffusion), une squad qui n'a pas
  bouge ne declenche rien.

Le bouton **Envoyer au squad leader** de la page d'une squad reste, pour l'admin
(`/api/admin/report-config/send-squad-leaders`).

### Reprise des anciens reglages

Les reglages d'avant les diffusions (un planning par tribe
`weekly_report:tribe:<id>` et celui de la Direction `weekly_report`, y compris la
toute premiere forme `global_doc`, `per_squad`, `squad_leaders`,
`tribe_leader_digest`, `attach_pptx`) sont convertis **une fois** en diffusions
(`reportconfig.ensure_diffusions`, au premier affichage du menu ou au premier
passage du planificateur). Chacun garde son calendrier, ses destinataires, le jour
de son dernier envoi et ses references « quoi de neuf » : personne ne recoit un mail
en double ni ne perd les nouveautes de la semaine. `leader_mode` « tribe » devient
`leader_tribe`, « per_squad » devient `leader_squads`, les adresses fixes de la
Direction deviennent des destinataires par adresse. Un planning jamais regle
(desactive, sans destinataire) n'est pas repris. La table des anciens abonnements
personnels reste en base mais n'est plus lue.

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
defaut, le tribe leader a ma tribe, comptes, conges et rapports par mail ; les
autres personas n'ont aucun onglet.

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
| Diffusions et reprise des anciens reglages | `backend/app/reportconfig.py`, `backend/app/mailplan.py` (qui recoit quoi), `backend/app/report.py` (`_send_schedule`, `send_plan_now`, `plan_preview`, `history`, `next_send`) |
| Routes des diffusions | `backend/app/routers/diffusions.py` (`/api/admin/diffusions`) ; `routers/admin.py` garde `/report-config/send-squad-leaders` |
| Mail de modification | `backend/app/changenotify.py`, `backend/app/changeconfig.py` |
| Onglets par persona | `backend/app/personasconfig.py`, `backend/app/tabaccess.py`, `backend/app/deps.py` |
| Ecrans | `frontend/src/components/ReportsMail.tsx` (menu Rapports par mail), `frontend/src/pages/admin/configuration.tsx`, `frontend/src/pages/admin/organisation.tsx` |
| Tests | `backend/tests/test_mail_plan.py`, `test_report.py`, `test_changenotify.py`, `test_rbac_admin.py`, `test_otds.py` |
