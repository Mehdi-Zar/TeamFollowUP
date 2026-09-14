# 27 - Le parcours de reporting, et les trois listes du tableau de bord

## 1. Le reporting devient ce qu'il est : un parcours

**Ce que l'ecran disait et ce qu'il faisait ne coincidaient pas.** En tete, une
bande decorative annoncait six temps. En dessous, huit cartes empilees sur une
page qui defile : sans ordre visible, sans indication de ce qui restait a faire,
et sans rapport avec les six temps annonces. Le mode d'emploi decrivait une
demarche que l'ecran ne proposait pas.

La bande devient donc la navigation. C'est le changement, et il tient en une
phrase : **un mode d'emploi qui ne fait pas avancer se lit une fois puis se
saute ; celui-ci est le chemin lui-meme.**

- **Une etape a la fois.** On voit ce qu'on remplit, on sait laquelle c'est, et
  la barre dit ce qui est deja renseigne (✓), ce qui reste, et ce qui est
  facultatif.
- **Rien n'est bloquant.** Un etat n'est pas une condition de passage : on peut
  sauter une etape, on veut seulement qu'elle le dise. Une squad a le droit de
  n'avoir ni KPI ni action de comite.
- **Les etapes sont construites a partir des services actifs.** Une installation
  sans KPI ni steerco n'affiche pas d'etape vide : une etape qu'on traverse sans
  rien faire apprend a traverser les etapes. C'est pour la meme raison que les
  actions de comite n'en sont pas une : elles se decident en comite et se
  relisent entre deux, pas au rythme du reporting. Elles vivent sur la page de la
  squad, a cote des messages cles et de la comitologie, qui sont le meme sujet.

- **La couleur y dit un etat, pas une etape.** Chaque etape a d'abord eu sa
  teinte, six couleurs en rang dont un violet etranger a la charte. Elles ne
  disaient rien : le moral n'est pas orange et l'envoi n'est pas rouge. L'icone
  est donc monochrome, encre pour l'etape courante, verte pour ce qui est
  renseigne, grise pour le reste. Quand tout est colore, le rouge d'un jalon
  bloque ne se voit plus.
- **Rien n'est retire.** Ce sont les memes panneaux, dans le meme ordre, avec les
  memes droits. Seul l'empilement disparait.

### Le bandeau : quel reporting, pour qui

Avant le parcours, un bandeau dit en toutes lettres ce qu'on est en train de
remplir : la squad, la semaine ISO avec ses deux bornes, le jour, l'annee, et la
date du dernier envoi.

C'est ce qu'on verifie avant de saisir quoi que ce soit, et rien ne le disait :
ni la date ni la semaine n'apparaissaient nulle part. Quelqu'un qui suit
plusieurs squads n'avait aucun moyen de s'assurer qu'il remplissait la bonne.

La semaine est numerotee en ISO, celle des calendriers d'entreprise : la semaine
commence le lundi, et la semaine 1 est celle qui contient le premier jeudi de
l'annee. Compter autrement donnerait un numero different de celui que porte
l'invitation du comite. Les deux bornes sont affichees parce qu'un numero seul ne
se verifie pas.

### Deux manques que le passage en etape a fait apparaitre

- **Le commentaire du moral** existait en base, partait dans les documents, et
  aucun ecran ne permettait de l'ecrire. Il arrive sur l'etape Moral, la ou la
  question est posee : dans un coin d'entete, un champ de texte n'aurait eu ni la
  place ni le sens. Cette etape vient **apres les messages cles** : on dit d'abord
  ce qui s'est passe, puis comment l'equipe le vit, plutot que de se prononcer
  avant d'avoir relu sa semaine.
- **La liste de controle d'avant-envoi** ne s'affichait que dans la fenetre de
  confirmation, c'est a dire au moment ou il est trop tard pour y faire quelque
  chose. Elle est montree aussi sur la derniere etape, ou l'on peut encore revenir
  en arriere.

## 2. Quatre ecrans de liste, une seule facon de les piloter

L'apercu avait une recherche, un tri visible et une vue liste. Le steerco, les
initiatives et la roadmap n'avaient rien. Les trois montrent pourtant la meme chose : une
collection d'objets qu'on parcourt. Trois ecrans qui se ressemblent doivent se
piloter pareil, sinon chacun s'invente sa convention et l'on reapprend a chaque
onglet.

La barre est desormais un composant (`components/listView.tsx`) : une recherche,
un tri en boutons dont le critere actif porte le sens et le retourne au reclic, et
un choix entre cartes et liste. Le tri, son sens et la densite sont retenus d'une
visite a l'autre, par ecran, dans le navigateur de celui qui regarde.

| Ecran | Tri | Vue par defaut |
|---|---|---|
| Apercu | risque, avancement, nom, fraicheur | cartes |
| Steerco | nom, etat, mise a jour | cartes |
| Initiatives | intitule, owner, squad, echeance | liste (une initiative se lit en colonnes) |
| Roadmap | tribu, nom, avancement | la matrice, qui est deja une vue |

La roadmap ajoute ce qui lui manquait le plus : **le choix des squads affichees**.
A onze squads sur quatre trimestres, la matrice se lit en diagonale et l'on cherche
la sienne du doigt ; on coche desormais celles qu'on veut voir. Rien de coche veut
dire toutes, et le bouton le dit.

### Le steerco se replie

Il affichait d'un coup le document de toutes les plateformes dans un cadre de 1180
pixels : a deux plateformes c'est long, a dix c'est illisible, et la seule facon
d'en regarder une etait de la choisir dans une liste deroulante qui ne disait ni
son etat ni qui la retenait.

Chaque plateforme est maintenant une ligne fermee qui porte ce qu'on veut savoir
avant d'ouvrir : remplie ou non, ses contributrices, et qui manque. On ouvre celle
qu'on veut lire, et **c'est elle que l'export vise** : ce qu'on regarde et ce
qu'on emporte doivent etre la meme chose.

## Ou est le code

| Role | Fichier |
|---|---|
| Le parcours, la barre d'etapes, le bandeau | `frontend/src/pages/EntryPage.tsx` |
| Le commentaire du moral | `frontend/src/components/TeamMood.tsx` |
| La barre de lecture partagee | `frontend/src/components/listView.tsx` |
| Le steerco repliable | `frontend/src/components/SteercoConsolidation.tsx` |
| Les initiatives | `frontend/src/pages/InitiativesPage.tsx` |
