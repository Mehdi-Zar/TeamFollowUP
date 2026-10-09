# 36. Statut des OTD : règles et cas particuliers

Un OTD est une promesse datée, tenue par les jalons qu'on y rattache. Son statut
n'est jamais saisi tel quel : il se recalcule à chaque lecture, à l'écran comme
dans les exports et les mails, par une seule fonction (`status.otd_state`, dans
`backend/app/status.py`). Ce document fixe les règles et la façon de traiter
chaque cas, y compris le démarrage de l'outil en cours d'année.

## Les statuts

| Statut | Couleur | Sens |
|---|---|---|
| Dans les temps | bleu | rien ne menace la date |
| À risque | orange | la date est menacée (voir les raisons ci-dessous) |
| En retard | rouge | la date est dépassée et tout n'est pas terminé |
| Livré | vert | tous les jalons sont terminés, au plus tard le jour de la date |
| Livré en retard | orange | tous les jalons sont terminés, le dernier après la date |
| À cadrer | gris | aucun jalon rattaché : rien ne permet de juger |
| Non livré | rouge | reporté sur l'année suivante, ou déclaré tel à la main |
| Annulé | gris | abandonné ou déscopé, avec un motif |

## L'ordre des règles

La première règle qui s'applique donne le statut.

1. **Annulé** : l'OTD a été annulé (le motif est obligatoire).
2. **Statut déclaré** : un statut saisi à la main (Livré, Livré en retard, Non
   livré) l'emporte sur les jalons tant qu'il existe. Le retirer revient au calcul.
3. **Reporté** : un OTD reporté sur l'année suivante est « Non livré » dans son année.
4. **Sans jalon** : « À cadrer », puis « En retard » une fois la date passée.
5. **Tous les jalons terminés** : « Livré », ou « Livré en retard » si le dernier
   jalon a été terminé après la date d'engagement.
6. **Date dépassée** : « En retard », dès le lendemain de la date (aucune tolérance).
7. **À risque** si au moins une de ces raisons est vraie :
   - un jalon est bloqué ;
   - un jalon est à risque ;
   - la date est dans moins de 15 jours (`OTD_DUE_SOON_DAYS`) ;
   - un jalon non terminé est prévu dans un trimestre qui finit après la date (le
     plan ne tient pas la date ; l'écran nomme le jalon).
8. Sinon : **Dans les temps**.

L'API rend le statut et ses raisons (`reasons`). L'écran les montre dans
l'infobulle du statut et dans la fenêtre de l'OTD, avec la liste des règles
(« Comment ce statut est calculé ? »).

## Ce qu'on retient pour juger

- **La date de fin d'un jalon** (`roadmap_items.done_at`) est posée quand il passe
  à « Terminé », et effacée s'il en sort. Un jalon terminé avant l'existence de
  cette date est considéré comme terminé à temps.
- **La date initiale** (`otds.initial_committed_date`) est figée à la première
  saisie. Déplacer la date est une replanification : l'OTD est jugé sur la date
  actuelle, et l'écran affiche « Replanifié (+N j) » avec la date initiale.

## Les cas particuliers

### Démarrer l'outil en cours d'année

Pour un OTD dont l'histoire précède l'outil (par exemple une promesse de mars
saisie en octobre), on ne rejoue pas ses jalons après coup : on le crée avec sa
date et on **déclare son statut** (Livré, Livré en retard, Non livré), avec la
date constatée et un commentaire. Ce statut l'emporte sur les jalons rattachés
ensuite, et l'écran le signale (« Statut déclaré à la main »). Un OTD encore en
cours se crée normalement et suit le calcul.

### Un OTD abandonné ou déscopé

On l'annule depuis sa fenêtre, avec un motif obligatoire. Il reste visible et
daté, avec le motif, et sort des compteurs de retard. On peut annuler l'annulation.
Un OTD annulé n'est plus proposé dans la liste des OTD d'un jalon.

### Un jalon qui glisse sur l'année suivante

Le lien vers l'OTD **reste** : la promesse n'est pas tenue tant que ce jalon n'est
pas fait. L'OTD le compte, signale « Glissé sur une autre année », et passe
« À risque » (le jalon est prévu après la date) ou « En retard ». Enregistrer la
fenêtre de l'OTD, qui ne liste que les jalons de son année, ne le détache pas ;
on le détache depuis la fenêtre du jalon, où l'OTD apparaît comme « OTD d'une
autre année ». Un nouveau rattachement, lui, reste limité aux jalons de l'année
de l'OTD.

### Un OTD pas livré au 31 décembre

Le 1er janvier, le traitement périodique (`app/otdcarry.py`, lancé toutes les
heures et sans effet le reste de l'année) reporte chaque OTD d'une année passée
qui n'est ni livré, ni annulé, ni déclaré :

- **une copie** est créée sur l'année suivante : même titre, description, portée,
  squad et porteur, sans date (à replanifier), marquée « Report de l'OTD N » ;
- **ses jalons non terminés suivent** : un jalon encore dans l'année N est copié
  au T1 de N+1 (l'original reste dans la roadmap de N, tel qu'au 31 décembre), un
  jalon qui avait déjà glissé sur N+1 rattache son lien à la copie ;
- **l'original reste dans l'année N**, « Non livré », avec ce qui était fait, et
  affiche « Reporté sur N+1 » ;
- **le tribe leader** (OTD de la tribe), ou **le squad leader** (OTD de la squad),
  ainsi que le porteur, reçoivent une notification.

Un jalon qui tient à la fois un OTD de la tribe et un OTD de la squad n'est copié
qu'une fois, et la copie porte les deux liens. Le report ne se fait qu'une fois
par OTD. Un OTD créé après la fin de son année (saisi après coup pour être
déclaré) n'est jamais reporté.

### Un OTD de la tribe tenu par plusieurs squads

Le statut est global et suit les règles ci-dessus. Sur la page d'une squad, la
ligne de l'OTD montre aussi **la part de cette squad** : ses jalons terminés sur
son total, et combien sont en retard (trimestre fini, pas terminé).

## Dans les exports et les mails

Les documents lisent le même statut. Les compteurs « OTD en retard » ne comptent
que le statut « En retard » : un OTD annulé, livré en retard ou reporté n'y entre
pas. Les versions figées d'un document gardent le statut qu'elles avaient.
