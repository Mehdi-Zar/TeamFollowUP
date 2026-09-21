# 24 - Les exports d'une squad : la frise de l'annee et le moral

Les trois documents que produit l'application pour une squad (HTML, JPG, PPTX)
posaient l'annee en trois blocs separes, comme le faisait l'ecran : les
initiatives, les engagements OTD, puis une roadmap en quatre colonnes de
trimestre. Ils la posent maintenant sur un seul axe.

**L'ecran, lui, n'a pas change.** Il garde ses trois cartes. Ce document ne parle
que de ce qui est genere et distribue.

## 1. Un bloc au lieu de trois

Le bloc unique met tout sur **le meme axe**, parce que le temps est la seule
chose que ces trois objets ont en commun :

1. **Les trimestres**, avec l'avancement calcule de chacun. Le commentaire du
   trimestre, lui, n'est pas sur la slide : il s'inserait entre l'en-tete du
   trimestre et la bande des mois, ou il coupait la lecture de l'axe juste la ou
   elle commence. Il reste a l'ecran et dans le rapport HTML, qui n'ont pas de
   hauteur a tenir.
2. **Les mois**, qui donnent la resolution de l'axe, sur une bande et non sur le
   blanc de la carte : douze mots poses dans le vide ne forment pas une regle, et
   c'est une regle qu'on cherche quand on suit une date. Un mois sur deux est
   legerement plus fonce, pour que l'oeil compte les colonnes sans lire les noms.
3. **Les engagements OTD**, poses a leur date juste sous les trimestres : c'est
   la promesse tenue ou non que le comite regarde en premier. Tous de la meme
   couleur, celle de la marque : une rangee d'engagements de quatre teintes ne
   laisse plus ressortir les jalons en dessous, dont la couleur dit un risque. Le
   statut reste ecrit, ce qui se lit aussi en noir et blanc.
4. **Une ligne par initiative**, portant **les jalons qui la servent**, chacun
   dans son trimestre. La colonne de gauche est titree, comme l'est la bande des
   engagements : sans ce mot, on y trouvait un nom suivi d'une personne et d'une
   date, sans rien qui dise de quoi il s'agit.

**Une ligne d'initiative, ce sont les jalons qui la servent**
(`RoadmapItem.initiative_id`), et ce lien se pose dans « Mes squads », a l'etape
OTD, du meme geste que les jalons d'un engagement.

Il a d'abord ete indirect, un jalon repondant a un objectif annuel qui servait une
initiative. Personne ne pouvait poser le second maillon : aucun ecran n'offrait
« cet objectif sert telle initiative ». Chaque frise affichait donc des lignes
d'initiative vides et une ligne anonyme portant tous les jalons, ce qui ressemblait
a une mise en page ratee alors que c'etait une donnee jamais saisissable. L'ancien
chemin reste lu en second, pour des donnees qui n'auraient pas ete reprises.

L'objectif annuel, lui, garde son seul vrai role : etre un objectif qu'on suit,
dont la page de synthese compte les rouges. Il n'apparait pas sur cette frise.

### Ce que la frise n'a pas le droit de perdre

Un document qui part en comite ne peut pas taire ce que les trois blocs
disaient. Trois cas sont traites explicitement, et chacun a son test :

- **Un jalon qui ne sert aucune initiative** garde sa ligne, « Jalons hors
  initiative », plutot que de disparaitre. Un jalon absent d'un export se lit
  comme un jalon qui n'existe pas. Il en va de meme d'un jalon rattache a une
  initiative portee par une autre squad.
- **Un engagement sans date** n'a pas de place sur l'axe : il est cite sous la
  bande.
- **La dependance d'un jalon** suit sur sa boite : c'est souvent la seule ligne
  qui explique un glissement.
- **L'owner d'une initiative et son echeance** ne sont pas sur la frise. Ils y ont
  figure sous le nom de l'initiative, ou ils ne repondaient a rien : la ligne dit
  quels jalons servent quoi, pas qui la porte. Ils se lisent sur le document des
  initiatives, sur la carte des initiatives de la page d'une squad, et dans
  « Mes squads ».
- **La phase d'un jalon, EA ou GA**, se lit a droite de son titre dans la boite,
  dans une colonne de largeur fixe pour que le titre sache ou s'arreter. Elle est
  en encre de service et non aux couleurs de la phase : le bord gauche de la
  boite porte deja une couleur, celle du statut, et deux codes couleur dans une
  boite de deux centimetres ne se distinguent plus de loin. Les deux lettres ont
  leur legende au bas de la slide, a cote de celle des couleurs.
  La dependance, elle, reste hors de la boite sur la slide : a trois
  informations sur une ligne, c'est le titre qui etait coupe, et c'est la seule
  qu'on lit de loin. Le HTML, qui n'a pas de bas de page a tenir, garde les deux.

### Un engagement est une date, pas une duree

Le repere est un losange pose sur le mois, et le titre s'ecrit a cote. Il a
d'abord ete dessine comme une pastille pleine occupant plusieurs mois, pour loger
ce titre : une forme qui s'etire se lit comme une periode, elle disait « de
septembre a novembre » la ou la donnee dit « le 30 septembre ». La largeur etait
un besoin de mise en page, jamais une information.

### Deux engagements qui se genent

La place reservee au titre suit sa longueur, exprimee en mois. Quand deux se
recouvrent, le second descend d'une bande. En HTML le nombre de bandes n'est pas
limite ; sur une slide il l'est a quatre, parce que la hauteur d'une slide ne
s'etire pas, et ce qui ne tient pas est compte et affiche (`+2`) plutot que
supprime.

Le calcul est le meme pour les deux formats (`reportcommon.pack_otds`) : deux
mises en page qui se contrediraient sur la place d'un engagement seraient pires
qu'une seule imparfaite. Seule la densite de texte change, huit caracteres par
mois en HTML, treize sur une slide en 9 pt.

**Un engagement de novembre ou de decembre n'a plus rien devant lui.** La largeur
reservee au titre s'arrete a la fin de l'annee, donc un engagement de decembre
dispose d'un mois et se coupe apres une quinzaine de caracteres. Sur ces deux
derniers mois, le titre s'ecrit donc **a gauche du repere**, dans ce que le
precedent de la meme bande laisse libre, et sur la slide seulement : mieux vaut
un titre entier a gauche d'un point qu'un titre coupe a sa droite. Ailleurs sur
l'axe il reste a droite, parce que le bord gauche du titre pose sur la date est
ce qui fait lire la bande. Quand la bande est deja occupee jusqu'au repere, il n'y
a pas de place a gauche non plus et le titre se coupe, ce qui reste honnete.

## 1 bis. Un engagement, une carte, ses jalons dedans

La frise groupait par initiative. Elle groupe desormais par **engagement OTD**,
avec les jalons qui le tiennent. La question posee en comite est « quels jalons
tiennent cette date » : une initiative est une intention, un engagement est une
date, et c'est la date qui est lue.

Les deux portees se distinguent par la couleur, la meme partout : bleu de marque
pour l'engagement du management, cyan profond pour celui que la squad prend
elle-meme. L'etoile posee sur l'axe, le titre de la carte et la legende partagent
cette couleur, et la legende figure sous la frise parce qu'une couleur sans
legende se devine, mal, en reunion.

Un jalon qui tient les deux engagements apparait dans les deux cartes : c'est le
meme travail lu par deux promesses, pas un doublon. Un engagement sans jalon garde
sa carte : c'est la promesse la plus fragile du lot, puisque rien n'est encore
pose pour la tenir. Les jalons qui ne tiennent aucun engagement se regroupent par
trimestre dans une carte sans titre : ils ne forment pas une categorie, ils sont
ceux qui n'en ont pas.

Les initiatives ne figurent plus sur la slide du dashboard. Elles gardent leur
propre document (`render_initiatives_pptx`) et leur carte a l'ecran.

### Pourquoi des cartes, et pas des lignes (slide PPTX)

Une ligne par engagement obligeait a couper chaque titre a la largeur d'une
colonne de trimestre, et un titre coupe ne dit plus rien : personne ne peut
deviner ce qui manque. Dans une carte, la largeur est fixe et le texte passe a la
ligne, donc il se lit en entier. C'est la seule regle a laquelle la mise en page
ne deroge pas.

Le rangement suit une **grille de colonnes** (cinq, six ou sept selon la charge).
Une carte va dans la colonne de son mois et s'empile sous celles qui y sont deja ;
si cette colonne est pleine jusqu'en bas, elle prend la moins remplie, et sa date
reste ecrite dans son en-tete. Le placement libre a ete essaye d'abord : deux
cartes decalees d'un demi-mois se genent sans qu'aucune n'utilise la place
restante, et une carte de decembre finissait comptee en « +1 » alors que le milieu
de la frise etait vide.

Quand tout ne rentre pas, l'ordre est : ajouter une colonne, puis reduire le corps
(9,5 pt jusqu'a 7,5 pt), et seulement en dernier recours compter en clair ce qui
n'a pas de place. Jamais couper un texte.

Une etoile marque la date sur l'axe et un pointille la relie a sa carte, mais
seulement quand la carte est restee pres de son mois : quand elle a ete rangee
ailleurs, le trait traverse la frise en diagonale et croise les autres, ce qui
coute plus en bruit qu'il ne rapporte, alors que la date ecrite dans la carte dit
deja a quel repere elle repond.

Dans chaque carte, un jalon est une puce dont la couleur porte le statut, avec sa
phase (EA ou GA) en gris derriere son titre. La legende du bas traduit les deux
codes, une fois pour toute la slide.

## 2. Le moral de l'equipe

Chaque document porte le moral declare par la squad, en haut a droite : un petit
nuage, vert quand ça va bien, ambre quand c'est moyen, rouge quand ça ne va pas,
avec la date rangee en petit dans le coin de la carte. Elle date le moral, elle ne
le dit pas : sous le nuage, sur une troisieme ligne centree, elle prenait le meme
rang que le niveau, qui est la seule chose a lire de loin.

**Un nuage dessine, pas un emoji.** Un emoji depend de la police installee sur le
poste qui ouvre le document : il change de style d'un support a l'autre et sort en
carre la ou le jeu couleur manque. Le nuage est dessine, donc il sort partout
pareil : en SVG dans l'ecran et dans l'export HTML (`reportcommon.mood_cloud_svg`,
repris a l'identique par `MoodCloud` cote interface), en formes PowerPoint dans le
deck (un nuage, deux yeux, une bouche construite en polygone plutot qu'en arc,
dont le rendu dependrait de reglages que PowerPoint interprete). La bouche redit
le niveau que la couleur donne, pour qui imprime en noir et blanc.

**Trois niveaux et pas cinq.** Une echelle fine invite a la nuance, or ce qu'on
cherche ici est un signal. Trois choix se decident en une seconde, ce qui est la
condition pour que la case soit remplie chaque semaine plutot qu'une fois en
janvier.

**La date compte autant que le niveau.** Un moral de mars projete en septembre
ment plus surement qu'une case vide : l'age est toujours indique.

**Ou il se declare.** En tete de l'ecran de saisie, la ou l'on rend compte chaque
semaine, par ceux qui peuvent editer la squad : son responsable, ses
co-responsables, son tribe leader, un admin. C'est le moral de leur equipe, pas
une note qu'un tiers leur attribue. Il reste visible sur la page de la squad et
sur les cartes du tableau de bord. Recliquer sur le niveau
courant retire la declaration, ce qui est la seule facon de dire « je ne me
prononce plus » sans inventer un quatrieme niveau, et efface aussi la date, sinon
une date resterait a l'ecran sans rien dater.

Quand rien n'est declare, les documents ecrivent « non renseigne » sans nuage :
un nuage gris se lirait comme un quatrieme niveau, alors que « non renseigne »
n'en est pas un.

## 3. Les trois formats

| Format | Ce qui le produit | Remarque |
|---|---|---|
| HTML | `report.render_html` -> `_timeline_html` | Feuille de style embarquee, pour ne dependre d'aucun build |
| JPG | Le navigateur, a partir de ce meme HTML | `ExportMenu.renderHtmlToJpg`, donc rien a maintenir a part le HTML |
| PPTX | `reportpptx.render_pptx` -> `squad_slide` | Une squad, une slide, 13,33 x 7,5 pouces |

Le deck suit le modele fourni : bandeau de titre avec le responsable, moral en
haut a droite, la grande carte de la frise, puis les messages cles et le budget
en bas. Un export de plusieurs squads garde sa page de synthese en tete ; un
export d'une seule squad est le meme deck sans elle.

Ce qui ne tient pas dans une forme est coupe sur des points de suspension.
PowerPoint ne sait pas le faire seul : sans coupe il passe a la ligne et le texte
sort de la pastille.

### Lisible depuis le fond de la salle

Un deck se projette. Les corps de texte de la slide d'une squad sont donc donnes
pour une lecture a distance (9 pt pour un titre de jalon ou un engagement, 10 pt
pour les messages cles et le budget), et l'encre est un noir presque franc
(`#111827`) : sur un videoprojecteur fatigue, un gris anthracite perd la moitie
de son contraste et le texte se devine au lieu de se lire.

Le filet de couleur au bord d'un jalon porte son statut, et il a sa **legende en
bas de slide** : une couleur sans legende se devine, et se devine mal quand on
decouvre le document en reunion.

## 4. La frise a pleine charge

Une mise en page ne casse pas sur un cas, elle casse quand tout arrive ensemble.
Le jeu de donnees de demonstration (`app.seed_fake`) sert donc aussi de cas de
charge : neuf jalons par squad tires d'un catalogue de titres de longueurs
variees, un trimestre qui en porte parfois trois, des objectifs rattaches a des
initiatives pour que la frise ait plusieurs lignes, une ligne de jalons qui ne
sert aucune initiative, et cinq engagements par squad dont certains en novembre
et en decembre.

Il a longtemps porte cinq jalons de titre court, jamais plus de deux par
trimestre, aucun objectif rattache a une initiative, et **aucun engagement** :
la bande du haut ne se dessinait jamais et la frise n'avait qu'une ligne quel que
soit le nombre de jalons. Une mise en page se validait alors sans avoir rien eu a
ranger. `backend/tests/test_export_timeline_dense.py` tient les deux bouts : que
ce jeu reste dense, puis qu'a cette densite rien ne sorte de la slide et qu'aucun
titre d'engagement n'en recouvre un autre.

## 5. Ou est le code

| Role | Fichier |
|---|---|
| Le regroupement des jalons par initiative, le rangement des engagements | `backend/app/reportcommon.py` (`timeline_rows`, `pack_otds`) |
| La frise en HTML et sa feuille de style | `backend/app/report.py` (`_timeline_html`, `_TIMELINE_CSS`) |
| La slide d'une squad | `backend/app/reportpptx.py` (`squad_slide`) |
| Le JPG, rendu depuis le HTML | `frontend/src/components/ExportMenu.tsx` |
| Declarer le moral | `frontend/src/components/TeamMood.tsx`, `PUT /api/squads/{id}/mood` |
| Le jeu de donnees de demonstration | `backend/app/seed_fake.py` |
| Tests | `backend/tests/test_export_timeline.py`, `backend/tests/test_export_timeline_dense.py`, `backend/tests/test_mood.py` |
