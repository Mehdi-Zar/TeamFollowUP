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
- **Numerotee, et flechee.** Chaque etape porte son rang dans une pastille, qui
  devient un ✓ quand elle est remplie, et un chevron separe deux etapes. Des
  cartes posees cote a cote se lisent comme un menu, ou l'on choisit ; une suite
  numerotee et flechee se lit comme un parcours, ou l'on avance. Le rang est
  repete en tete du panneau, pour qu'on puisse dire ou l'on est sans remonter les
  yeux. La pastille portait jusque la une icone par etape, mais deux etapes
  partageaient la meme et aucune ne nommait la sienne : un rang, lui, dit
  quelque chose.
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
- **Le passage en parcours n'avait rien retire.** C'etaient les memes panneaux,
  dans le meme ordre, avec les memes droits, et seul l'empilement disparaissait.
  Trois d'entre eux en sont partis depuis, pour la raison dite plus bas : une
  etape ou l'on ne peut rien faire n'est pas une etape.

### Une etape ou l'on ne peut rien faire n'est pas une etape

Trois etapes ouvraient sur quelque chose que leur lecteur ne pouvait pas ecrire.

**Les engagements OTD, les initiatives et les objectifs annuels** formaient la
premiere etape du parcours, trois cartes empilees sous un seul titre. Or ces trois
objets se fixent par un tribe leader ou un admin, et **un tribe leader n'a pas
acces a l'ecran de saisie** : la capacite `reporting` n'est pas dans ses droits par
defaut. Le parcours s'ouvrait donc, pour son lecteur reel qui est le squad leader,
sur trois panneaux en lecture seule.

Ils ne sont pas perdus, ils sont rendus a l'ecran ou l'on peut agir : « Mes
squads » pour les ecrire, la page de la squad pour les lire, ou le squad leader
les voit deja avec le reste de ce qui decrit son equipe.

**Les deplacer a montre un trou.** Le test de parite entre l'API et l'interface
(`test_api_ui_parity.py`) a refuse le changement : plus aucun ecran n'appelait
`POST /api/objectives`. L'editeur des OTD de l'annee n'existait donc **que** dans
l'ecran de saisie, reserve la aux tribe leaders et aux admins, alors qu'un tribe
leader n'y entre pas : en pratique, seul un admin pouvait creer un OTD, depuis un
ecran cense servir a autre chose. L'editeur est desormais dans « Mes squads », a
l'etape Options, avec les autres choses que la squad suit, ou l'intitule de
l'ecran promettait deja de les porter (« les OTD, definis par vous, le tribe
leader »). Pas a l'etape OTD malgre leur nom : celle-ci montre ce que la frise
exportee montre, et l'objectif annuel n'y figure pas. Il compte ailleurs, dans le
chiffre « objectifs rouges » de la page de synthese.

**Le Steerco** ne regardait que le module global. Une squad qui ne contribue a
aucune plateforme traversait quand meme l'etape, pour y lire « demandez a votre
tribe leader ». Elle ne s'affiche plus que si la squad alimente une plateforme
dont le steerco est actif. Le drapeau qui porte cette reponse existait deja
(`Squad.steerco_enabled`) mais comptait toute plateforme, y compris celles dont le
steerco est coupe : il compte desormais celles ou il y a reellement quelque chose
a saisir.

**Ce qui reste** est ce que le squad leader ecrit lui-meme : les jalons, ses KPI
s'il en a, le commentaire de chaque trimestre, les messages cles, le moral, puis
l'envoi. Une etape en moins n'est pas une information en moins : c'est un ecran de
moins a traverser pour trouver celui qui attend quelque chose de vous.

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
