# 26 - Ranger les ecrans : menus, valeurs par defaut, mode d'emploi

Un lot de rangement. Rien de neuf sur le fond : les memes fonctions, mises la ou
on les cherche, nommees comme on les nomme, et allumees seulement quand elles
servent.

## 1. « Tribus » et « Organigramme » n'etaient qu'un ecran

La page Tribus listait les tribus avec leur nombre de squads et ne savait faire
qu'une chose : ouvrir l'organigramme sur celle qu'on cliquait. L'organigramme
offrait deja le meme choix, dans une liste deroulante de son entete. Deux entrees
de menu pour une seule question, « quelle tribu je regarde », avec la mauvaise
moitie de la reponse de chaque cote : les cartes avaient le nombre de squads, la
liste deroulante avait le reste de l'ecran.

L'organigramme recupere ce que les cartes apportaient, sous la forme d'une rangee
de tribus cliquables qui remplace la liste deroulante. La page Tribus et son
entree de menu disparaissent.

L'organigramme s'ouvre maintenant sur **la liste**, l'arbre en second : l'arbre
est la belle vue, la liste est celle qui repond a « ou est ma squad » sans faire
defiler.

## 2. Le menu d'administration

Les quatre familles etaient nommees d'apres ce qu'elles contenaient, pas d'apres
la question a laquelle elles repondent, et leur contenu s'etait melange en route :
l'import au milieu de l'organisation, les sauvegardes rangees avec la moderation,
l'apparence a cote des reglages du rapport hebdomadaire.

Quatre questions, dans l'ordre ou on se les pose en montant une installation :

| Famille | La question |
|---|---|
| Organisation | qui est dans l'organisation : tribus, squads, plateformes, comptes, personas, **puis l'import** |
| Services et apparence | ce que l'application propose : services actifs, rapport hebdomadaire, conges, reglages generaux, apparence |
| Connexion et messagerie | comment on s'y connecte : authentification, email, cles d'API, autorites de certification |
| Exploitation | comment on l'entretient : journal d'audit, moderation, export des journaux, sauvegardes, maintenance |

L'import ferme la premiere famille : il sert une fois, au debut, et jamais plus.
Au milieu, il passait pour un reglage courant.

Les libelles suivent. « Donnees » ne disait pas ce qu'on y fait et personne n'ira
chercher une restauration derriere un mot aussi large : c'est **« Sauvegardes et
remise a zero »**. De meme « Ops / Maintenance » devient « Maintenance »,
« Import » devient « Importer une organisation », « Utilisateurs » devient
« Comptes », « Services » devient « Services actifs ».

## 3. L'import connait les plateformes

Une plateforme est le niveau auquel le comite lit les chiffres : elle regroupe les
squads qui l'alimentent, et c'est elle qui decide si une squad est au steerco. Le
fichier d'import savait declarer une tribu, ses squads, ses initiatives et ses
engagements, et s'arretait juste avant. Monter une organisation par import
laissait donc tout le steerco a faire a la main.

Un cinquieme onglet, **Plateformes** : nom, squads contributrices separees par des
virgules, description. Les squads sont resolues par leur nom comme partout
ailleurs dans ce fichier, et une squad inconnue est signalee dans le rapport
d'import plutot que silencieusement ignoree.

## 4. Ce qui est allume dans une installation neuve

Le fil et les conges sont **eteints par defaut**, comme l'etaient deja la
comitologie et le steerco. Ce sont des services en plus, pas le coeur du produit :
une installation neuve doit montrer ce dont elle a besoin et laisser allumer le
reste depuis Administration > Services actifs. Les installations existantes ne
bougent pas : leur reglage est enregistre et prime sur la valeur par defaut.

La suite de tests monte sa base avec ces services disponibles (`conftest`), parce
que la plupart des tests ne portent pas sur l'interrupteur mais sur ce qu'il y a
derriere. La valeur par defaut, elle, est gardee la ou elle est ecrite
(`test_modules.test_the_optional_services_start_off`).

## 5. Le tableau de bord : chercher d'un cote, afficher de l'autre

Les commandes de tri avaient ete remontees dans la carte des filtres, et s'y
noyaient. Chercher et filtrer reduit ce qu'on voit ; trier et changer de vue ne
fait que le reordonner. Les deux gestes n'ont pas a partager la meme carte : la
recherche et les filtres restent dans la leur, le tri et la vue passent a droite,
sur la ligne de la legende.

## 6. Le mode d'emploi du reporting

La bande d'en-tete de l'ecran de saisie decrivait un ecran qui a change : elle
commencait par les OTD alors que la premiere chose demandee est le moral, parlait
d'objectifs annuels la ou l'ecran parle d'engagements dates, et ne disait rien des
messages cles.

Six temps, dans l'ordre ou l'ecran les pose :

1. **Moral** : trois niveaux, une seconde.
2. **OTD** : les engagements dates de l'annee, poses par le tribe leader.
3. **Jalons** : les livrables par trimestre qui les rendent concrets.
4. **Statut** : en cours, a risque, bloque, termine.
5. **Messages cles** : un succes, une alerte, un risque.
6. **Soumettre** : figer l'etat du cycle.

La note de bas de bande garde son role : le pourcentage ne se saisit pas, il se
calcule a partir des jalons termines.

**Les messages cles rejoignent l'ecran de saisie.** Le mode d'emploi les annonce
comme une etape, et c'est juste : c'est ce que le comite lit en premier et ce qui
part en toutes lettres dans les documents. Ils ne se saisissaient pourtant que sur
la page de la squad, un ecran de lecture : celui qui rend compte devait en sortir
pour les ecrire, donc ne les ecrivait pas. Le panneau devient un composant employe
aux deux endroits, plutot qu'une copie dont une seule moitie serait corrigee.

## Ou est le code

| Role | Fichier |
|---|---|
| La barre des tribus de l'organigramme | `frontend/src/pages/OrgPage.tsx` |
| Les familles et l'ordre du menu admin | `frontend/src/pages/AdminPage.tsx`, `frontend/src/perms.ts` |
| L'onglet Plateformes du fichier d'import | `backend/app/import_org.py` |
| Les services allumes d'origine | `backend/app/modulesconfig.py` |
| Le mode d'emploi du reporting | `frontend/src/pages/EntryPage.tsx` |
| Les messages cles, composant partage | `frontend/src/components/KeyMessagesPanel.tsx` |
