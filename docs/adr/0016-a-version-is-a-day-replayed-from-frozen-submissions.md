# ADR 0016 - Une version est une journee, rejouee depuis les saisies figees

Statut : accepte. Prolonge le cycle de reporting (soumission = `ReportSnapshot`)
et l'ADR 0007 (statuts derives), qui explique pourquoi un statut recalcule
aujourd'hui ne peut pas servir a dater un document d'hier.

## Contexte

Une squad fige sa saisie a chaque soumission de cycle : objectifs, jalons,
avancement, KPI, le tout serialise dans `report_snapshots.payload`. Cette photo
ne se lisait que d'un seul endroit, l'historique de la page d'une squad, une
soumission a la fois, et sous deux formes : le diff avec la precedente, ou le
payload brut.

La question posee apres coup n'est pas celle-la. En comite comme en audit, elle
s'enonce : « montre-moi le dashboard tel qu'il etait le 12 septembre ». Un diff
ne la satisfait pas, un payload brut non plus, et l'export du jour encore moins.
Le seul recours etait de restaurer une sauvegarde de la base entiere, c'est a
dire de faire reculer l'application pour tous ses utilisateurs pour repondre a la
question d'un seul.

## Options examinees

1. **Archiver les documents produits** (le PPTX et le HTML de chaque semaine).
   Fidele par construction, puisque c'est le fichier lui-meme. Mais la mise en
   page bouge, et un document archive ne se regenere pas dans le format d'apres :
   six mois plus tard, la moitie des versions sortent dans une frise que plus
   personne ne reconnait. Et un document est un binaire : on ne peut pas y
   compter les jalons bloques, ni le filtrer selon qui le lit.
2. **Journaliser chaque changement** (table d'evenements, etat reconstruit par
   rejeu). Repond a n'importe quelle date, a la seconde pres. Mais c'est un
   second modele de donnees a maintenir a cote du premier, alors que la question
   posee ne porte jamais sur une seconde : elle porte sur la version qui est
   partie en comite, c'est a dire sur une soumission.
3. **Rejouer le document depuis les saisies deja figees**, en prenant pour chaque
   squad sa derniere soumission anterieure a la date demandee.

## Decision

La troisieme. Une **version est une journee** : `?as_of=2026-09-12` sur
`dashboard`, `roadmap` et `weekly`, dans les trois formats. `GET
/api/reports/versions` liste les jours ou une squad du perimetre a soumis, avec
le nombre de squads concernees, parce que c'est ce chiffre qui dit si la version
est complete.

Le rejeu ne recalcule rien : `reportasof.freeze_report_data` part du rapport du
jour, deja assemble et deja filtre pour ce lecteur, et remplace le contenu de
chaque squad par celui de sa saisie figee. Les compteurs (jalons bloques, a
risque, objectifs rouges) sont recomptes **sur les jalons figes** : un jalon
debloque depuis aurait fait etat de zero bloqueur dans une version qui en
comptait trois, ce qui est exactement le mensonge qu'on cherche a eviter.

La saisie figee a donc ete etendue a ce que les documents lisent : engagements
OTD avec leur date et leur portee, rattachements `otd_id` / `squad_otd_id` des
jalons, initiatives, messages cles, moral, avancement annuel et statut de la
squad. Sans eux, une version passee se serait reconstruite avec les liens et les
dates d'aujourd'hui.

## Ce que la version ne reprend pas, et pourquoi c'est dit

- **Une squad qui n'avait rien soumis a cette date sort du document**, et son nom
  est cite en tete. La remplacer par son etat du jour aurait donne un document
  complet en apparence et faux en un point, ce qui est le pire des deux.
- **Le budget est celui du jour.** Ses chiffres ne se montrent qu'aux
  responsables de la squad, alors qu'une saisie figee se lit par tout utilisateur
  qui voit la squad : les geler dans le payload les aurait ouverts a tout le
  monde. Le filtre de lecture reste donc celui de l'export.
- **Le nom de la squad et de son responsable** sont ceux d'aujourd'hui. Ce sont
  des etiquettes : une squad renommee depuis ne serait plus reconnue dans la
  liste sous son ancien nom.
- **Les absences a venir** disparaissent. Elles se projettent depuis aujourd'hui,
  et une liste d'hier presentee comme « a venir » tromperait plus surement qu'une
  liste vide.
- **Le perimetre de lecture reste celui d'aujourd'hui.** Une version passee n'est
  pas une porte derobee vers les squads d'une autre tribu.

Chaque document date porte la mention `version du ...` a cote de son heure de
generation, et le compte des squads sans saisie. Un document date qui ne se dit
pas date a l'air du rapport d'aujourd'hui et en donne les chiffres d'hier.

## Consequences

- Les sauvegardes de base (Administration > Donnees) gardent leur role, qui n'est
  pas celui-ci : restaurer l'application, pas relire un document.
- Une instance sans aucune soumission n'a aucune version : le selecteur de
  version n'apparait pas dans le menu d'export, qui reste ce qu'il etait.
- Les saisies anterieures a cette decision ne portent ni engagements, ni moral,
  ni messages cles. Elles restent lisibles : ce qu'elles n'ont pas sort vide, et
  non rempli avec la donnee du jour.
