# 21 - Donnees : remise a zero granulaire et sauvegardes

**Administration > Donnees**, reserve a l'administrateur. Tout se fait a l'ecran :
effacer ce qu'on choisit, prendre une copie des donnees, la restaurer, la
telecharger, en reimporter une, et programmer des copies automatiques.

Avant, il existait une seule facon de repartir de zero : `python -m app.reset_data`
dans le conteneur. Elle effacait tout et recreait une organisation codee en dur,
ne posait aucune question, et ne savait pas effacer une annee de saisies en gardant
l'organigramme.

## 1. Effacer ce qu'on choisit

L'ecran liste des **domaines**, pas des tables : ce qu'une personne a en tete quand
elle dit « les saisies » ou « la structure ». Chaque ligne indique le nombre de
lignes reellement en base, et ce que le domaine **entraine** avec lui.

| Domaine | Contenu | Entraine |
|---|---|---|
| Saisies hebdomadaires | instantanes de reporting, avancement trimestriel, messages cles, actions de revue, baselines | |
| Jalons de roadmap | `roadmap_items` | |
| Objectifs de squad | `objectives` | Jalons |
| Initiatives et OTD | `initiatives`, `otds` | |
| KPIs, Budgets, Comites, Membres, Organigramme, Absences, Fil, Notifications, Journal d'audit, Cles d'API | chacun ses tables | |
| Steerco et plateformes | `steerco_entries`, `platform_contributors`, `platforms` | |
| Tribus et squads | `squads`, `tribes`, co-responsables | tout ce qui pend a une squad ou une tribu |
| Comptes utilisateurs | abonnements, et via la politique de suppression de compte | Fil, Notifications, Absences, Cles d'API |

Les dependances sont **declarees**, pas devinees. Le graphe des cles etrangeres sait
qu'un jalon meurt avec sa squad ; il ne sait pas qu'un administrateur qui dit
« efface les saisies » ne dit pas « efface les squads ». Cocher un domaine surligne
en orange ceux qu'il entraine, et la fenetre de confirmation repete le total.

**Jamais efface**, quel que soit le choix : `app_settings` (SMTP, modules, SSO,
toute la configuration), `leave_types` (un referentiel), les sauvegardes
elles-memes, et le **compte de secours**. Perdre la configuration avec les donnees
fermerait la porte de l'application qu'on etait en train de ranger.

Une reference qui survit a ce qu'elle designe est **detachee** avant l'effacement
(`datareset.detach_external_refs`) : supprimer les tribus pendant que les comptes
pointent encore dessus echouerait sur la cle etrangere, et l'administrateur lirait
une erreur de base pour un choix que l'ecran lui a propose. Une reference **non
nullable** depuis une table qui survit fait echouer l'operation avec le nom du
couple fautif : cela veut dire que le graphe des domaines est faux, et c'est une
information, pas un incident.

Par defaut, une **sauvegarde est prise avant l'effacement**, dans la meme
transaction : la remise a zero laisse une copie derriere elle, ou n'a pas lieu.

## 2. Sauvegarder et restaurer

Une sauvegarde est le contenu des tables metier, serialise en JSON et compresse
dans une ligne de `data_snapshots`. En base plutot que sur un volume : elle suit
ainsi les sauvegardes `pg_dump` du sidecar et survit a une reconstruction du
conteneur. Cette application compte ses lignes en milliers, une copie pese quelques
centaines de kilo-octets.

Ce qu'une sauvegarde contient est exactement ce qu'une remise a zero peut effacer,
moins la configuration : `NEVER_ERASED` est la definition unique, donc une
sauvegarde ne peut pas emporter les identifiants SMTP ni les autres sauvegardes.

**Restaurer** vide les tables couvertes et y reecrit les lignes stockees,
**identifiants compris**, en une transaction. Garder les identifiants est ce qui
fait d'une restauration un retour en arriere et non une fusion, et c'est pourquoi
les sequences PostgreSQL sont reallignees ensuite : sans cela, la creation suivante
reutiliserait un identifiant deja restaure.

Une **copie de securite de l'etat courant** est prise avant chaque restauration :
restaurer la mauvaise ligne reste rattrapable.

**Telecharger** donne le fichier `.json.gz` tel qu'il est stocke ; **Importer** le
range comme une sauvegarde sans l'appliquer. Importer et restaurer sont deux
decisions, et seule la seconde efface quelque chose. Un fichier tronque ou etranger
est refuse a l'import, pas au milieu d'une restauration.

## 3. Automatique ou manuel

Desactive par defaut : prendre des copies des donnees de quelqu'un est sa decision.

Une fois active, le planificateur horaire en prend une quand la derniere copie
**automatique** depasse l'intervalle, puis supprime les automatiques au-dela du
nombre a conserver. L'echeance se mesure depuis la derniere copie et non depuis un
horaire memorise : un redemarrage, un changement d'heure ou une semaine d'arret ne
peuvent pas rendre une sauvegarde eternellement en retard.

La retention ne touche **jamais** les sauvegardes manuelles : quelqu'un les a prises
expres, seule cette personne devrait les retirer.

## 4. Droits et tracabilite

Tout est reserve a l'administrateur (`require_admin`) et **audite** : `data.reset`,
`data.snapshot`, `data.restore`, `data.snapshot.delete`, `data.snapshot.import`,
`data.snapshot_config`. Le detail de l'audit porte les domaines effaces et le
nombre de lignes par table, donc l'operation reste racontable apres coup.

Chaque appel destructeur exige `confirm: true` dans le corps. Ce n'est pas un
remplacant de la fenetre de confirmation : c'est ce qui empeche un POST egare ou un
curl rejoue de vider une base, puisque ces endpoints sont joignables avec un simple
cookie d'administrateur.

## 5. Ou est le code

| Role | Fichier |
|---|---|
| Catalogue des domaines, detachement, effacement | `backend/app/datareset.py` |
| Sauvegardes : creation, restauration, retention, automatique | `backend/app/datasnapshots.py` |
| API `/api/admin/data/*` | `backend/app/routers/data.py` |
| Table `data_snapshots` | `backend/alembic/versions/0031_data_snapshots.py` |
| Ecran Administration > Donnees | `frontend/src/pages/admin/data.tsx` |
| Tests | `backend/tests/test_data_reset.py` |

Le sidecar `pg_dump` (docker-compose, profil `backup`) reste en place et repond a
une autre question : il protege la machine, ces sauvegardes protegent la personne.
Voir aussi [19](19-plan-de-reprise.md) et [20](20-donnees-personnelles-et-retention.md).
