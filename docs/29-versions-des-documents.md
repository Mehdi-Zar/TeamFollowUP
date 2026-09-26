# 29 - Les versions d'un document : relire le dashboard d'une date passee

Le tableau de bord, la roadmap et le rapport hebdomadaire sortent avec la donnee
du jour. La question qu'on pose apres coup, en comite ou en audit, n'est pas
celle-la : c'est **« montre-moi le dashboard tel qu'il etait le 12 septembre »**.

Chaque export peut desormais y repondre.

## 1. Ou ca se prend

Dans le menu **Exporter**, une ligne **Version** en tete du groupe
« Telecharger » :

- **Aujourd'hui**, qui est le defaut et reste le cas courant ;
- une date par journee ou au moins une squad du perimetre a soumis sa saisie,
  suivie du nombre de squads concernees.

Ce nombre est ce qui dit si la version est complete : « 12/09/2026 (11 squads) »
sur un perimetre qui en compte treize signale que deux squads n'avaient rien
soumis ce jour-la.

Le choix vaut pour **tous les documents du menu** : HTML, JPG, PPTX, et l'envoi
par courriel. La ligne n'apparait pas tant qu'aucune saisie n'a ete soumise : une
instance neuve n'a pas de version a proposer.

## 2. D'ou vient la donnee

D'aucune archive de fichiers : des **saisies figees** que chaque squad produit en
soumettant son cycle (ecran « Saisie »). Pour chaque squad du perimetre, le
document reprend sa **derniere soumission anterieure a la date demandee**.

Une version n'est donc pas une photo de l'instant : c'est le dernier etat
rapporte par chaque squad a cette date, ce qui est exactement ce que le comite de
ce jour-la avait sous les yeux.

Les compteurs (jalons bloques, a risque, objectifs rouges, avancement) sont
**recomptes sur les jalons figes**. Un jalon debloque depuis aurait fait etat de
zero bloqueur dans une version qui en comptait trois.

## 3. Ce qui n'est pas rejoue, et qui est dit sur le document

Chaque document date porte la mention `version du ...` a cote de son heure de
generation, avec le compte des squads sans saisie. Un document date qui ne se
dit pas date a l'air du rapport d'aujourd'hui et en donne les chiffres d'hier.

| Ce qui vient de la version | Ce qui reste celui d'aujourd'hui |
|---|---|
| Jalons, statuts, phases, dependances, rattachements aux engagements | Le budget |
| Engagements OTD, leurs dates, leurs portees | Le nom de la squad et de son responsable |
| Objectifs et leur couleur, avancement par trimestre et commentaires | Le perimetre de lecture (qui voit quelles squads) |
| Messages cles, initiatives, moral et sa date | |

- **Le budget** ne se montre qu'aux responsables de la squad, alors qu'une saisie
  figee se lit par tout utilisateur qui voit la squad : le geler aurait ouvert
  ses chiffres a tout le monde. Le budget affiche est celui du jour, filtre comme
  il l'a toujours ete.
- **Les noms** sont des etiquettes : une squad renommee depuis ne serait plus
  reconnue dans la liste sous son ancien nom.
- **Une squad qui n'avait rien soumis a cette date sort du document**, et son nom
  est cite. La remplacer par son etat du jour aurait donne un document complet en
  apparence et faux en un point.
- **Les absences a venir** disparaissent d'une version : elles se projettent
  depuis aujourd'hui, et une liste d'hier presentee comme « a venir » tromperait
  plus surement qu'une liste vide.
- **Le perimetre de lecture reste celui d'aujourd'hui.** Une version passee n'est
  pas une porte derobee vers les squads d'une autre tribu.

## 4. Les saisies d'avant cette fonction

Une saisie figee avant la mise en place des versions ne porte ni engagements, ni
messages cles, ni moral : ces champs n'etaient pas captures. Elles restent
lisibles, et ce qu'elles n'ont pas sort **vide**, jamais rempli avec la donnee du
jour.

## 5. Ce n'est pas une sauvegarde

Administration > Donnees garde ses sauvegardes de base, et elles repondent a une
autre question : **restaurer** l'application, ce qui la fait reculer pour tout le
monde. Une version ne change rien a l'etat de l'application, elle produit un
document.

## 6. Par l'API

```
GET /api/reports/versions?year=2026[&tribe_id=&squad_id=&squad_ids=]
  -> {"year": 2026, "versions": [{"date": "2026-09-12", "squads": 11, "labels": [...]}, ...]}

GET /api/reports/dashboard.pptx?year=2026&as_of=2026-09-12
GET /api/reports/roadmap.html?as_of=2026-09-12
GET /api/reports/weekly.html?as_of=2026-09-12
POST /api/reports/weekly/email  {"to": "...", "as_of": "2026-09-12"}
```

`as_of` accepte une date (`AAAA-MM-JJ`, prise en fin de journee) ou un horodatage
ISO. Une valeur illisible rend **422** : un document rendu sur la date du jour se
lirait comme la version demandee.

## 7. Ou est le code

| Role | Fichier |
|---|---|
| Le rejeu d'un document a une date, la liste des versions | `backend/app/reportasof.py` |
| La saisie figee, et ce qu'elle porte | `backend/app/routers/snapshots.py` (`build_payload`) |
| Le parametre sur les exports | `backend/app/routers/reports.py` (`_data`, `/versions`) |
| Le choix dans l'interface | `frontend/src/components/ExportMenu.tsx` |
| La mention portee par les documents | `backend/app/reportcommon.py` (`version_suffix`) |
| Tests | `backend/tests/test_report_versions.py` |

La decision et les options ecartees : [ADR 0016](adr/0016-a-version-is-a-day-replayed-from-frozen-submissions.md).
