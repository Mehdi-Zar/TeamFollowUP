# 24 - Les exports d'une squad : la frise de l'annee et le moral

Les trois documents que produit l'application pour une squad (HTML, JPG, PPTX)
posaient l'annee en trois blocs separes, comme le faisait l'ecran : les
initiatives, les engagements OTD, puis une roadmap en quatre colonnes de
trimestre. Ils la posent maintenant sur **une grille**, la meme dans les trois
formats : les mois en colonnes, un theme par ligne, chaque repere pose sur sa
date.

**L'ecran, lui, n'a pas change.** Il garde ses trois cartes. Ce document ne parle
que de ce qui est genere et distribue.

## 1. La frise, de haut en bas

1. **Les trimestres**, avec l'avancement calcule de chacun. Le commentaire du
   trimestre n'est pas sur la slide : il s'inserait entre l'en-tete du trimestre
   et la bande des mois, ou il coupait la lecture de l'axe juste la ou elle
   commence. Il reste a l'ecran et dans le rapport HTML, qui n'ont pas de hauteur
   a tenir.
2. **Les mois**, juste sous les trimestres : un trimestre et ses trois mois se
   lisent ensemble, et rien ne doit s'inserer entre les deux. Sur une bande, et
   non sur le blanc de la carte : douze mots poses dans le vide ne forment pas
   une regle, et c'est une regle qu'on cherche quand on suit une date. Un mois
   sur deux est legerement plus fonce, pour que l'oeil compte les colonnes sans
   avoir a lire les noms.
3. **Les engagements OTD**, une etoile posee sur leur mois et leur titre juste
   dessous, **dans la largeur de cette case de mois**.
4. **Les boites de jalons**, en pointille, rangees dans l'ordre des dates, chacune
   titree et reliee a sa date par un trait.

## 2. Les trois regles qui tiennent la mise en page

Elles ne sont pas des preferences : chacune repond a une facon dont les versions
precedentes se sont defaites, et chacune a son test sur le jeu de donnees dense.

### Un engagement tient dans sa case de mois

Son titre passe a la ligne autant de fois qu'il le faut, mais ne deborde jamais a
droite ni a gauche. Ecrit a cote de son etoile, il courait sur trois ou quatre
mois : on ne savait plus a quelle colonne il repondait, et il fallait trois
bandes superposees la ou une suffit.

Deux engagements du meme mois se suivent **dans la meme colonne**, l'un sous
l'autre. Cote a cote, chacun aurait un centimetre de large.

### Une boite ne sort jamais de son trimestre

Une boite par engagement, portant les jalons qui le tiennent; une boite par theme
et par trimestre pour les jalons qui n'en tiennent aucun. Une boite a donc **un
titre et une seule date**, ce qui est la condition pour qu'un trait suffise a dire
quand ses jalons sont attendus.

Chacune est posee dans les **trois colonnes du trimestre de sa date**, et n'en
sort pas. Elle peut commencer un mois plus tot que cette date pour y tenir : une
boite a cheval sur deux trimestres se lisait sous le mauvais, et une boite de
decembre n'avait nulle part ou s'etendre.

Les boites d'un meme trimestre **s'empilent sur une seule colonne**, chacune large
de tout le trimestre. On n'en ouvre une deuxieme, puis une troisieme, que lorsque
la pile ne tient plus dans la hauteur, ce qui est rare : la frise a de la hauteur
et peu de largeur. Deux boites cote a cote dans un trimestre font six centimetres
chacune, et leur texte casse tous les dix caracteres ou descend de deux points de
corps ; empilees, elles portent le meme texte en onze points sans couper un mot.

**Seule la tete de chaque pile recoit son trait** : un trait vers une boite du
bas traverserait celle du haut. Les suivantes portent leur mois devant leur titre
(« Sept - Bascule des environnements internes »), ce qui dit la meme chose sans
rien croiser.

Le corps du texte suit la charge : onze points et demi quand la slide est aeree,
et il descend jusqu'a six et demi plutot que de renoncer a une boite. Un jalon
ecrit petit se lit encore, un jalon absent ne dit plus rien. On ne renonce a une
boite qu'en tout dernier recours, et elle est alors citee sous la frise, ce qu'un
test interdit sur le jeu dense.

La bande des engagements est bornee de la meme facon, mais plus severement : une
case de mois est etroite, et son corps ne monte a neuf points que si aucun titre
n'y coupe un mot en deux. Il descend d'un cran tant que la bande depasse un pouce
de haut, parce que deux engagements du meme mois y occupaient la moitie de la
frise. Le plus grand corps qui tienne la hauteur **sans couper un mot** est
prefere : « interruption » scinde au milieu d'un titre se lit plus mal que le meme
titre ecrit un demi-point plus petit.

### Le trait remonte droit jusqu'au mois, par le cote

Il a **le meme ton et le meme pointille que la boite** : il fait partie du meme
dessin et ne doit pas se voir davantage qu'elle. Il part d'un point pose sur le
filet de la bande des mois et descend **tout droit** jusqu'au haut de sa boite.
Son ombre est explicitement retiree : PowerPoint en pose une par defaut, qui
doublait le trait d'un halo gris et le rendait plus lourd que l'encadre.

Pour passer, il longe le **bord** de la case du mois : la case d'un engagement est
inseree de sept centiemes de pouce de chaque cote, ce qui laisse a chaque
frontiere de mois un couloir libre sur toute la hauteur de la bande. Le trait ne
peut donc croiser aucun titre, quoi qu'il arrive.

Quand une boite a recule d'un mois pour tenir dans son trimestre, le trait reste
sur son vrai mois et le coude tient dans les quelques millimetres juste au-dessus
d'elle : mieux vaut un petit decrochement qu'une date fausse.

C'est ce qui remplace le routage. Les versions precedentes faisaient passer ces
traits au milieu des titres, puis derriere eux, puis dans les couloirs libres
entre eux, puis en coudes dans une gouttiere : a chaque etape la mise en page
tenait sur le cas qu'on venait de regarder et cassait sur le suivant.

### Ce que les tests tiennent

Sur les treize slides du jeu de donnees dense : aucun texte n'en recouvre un
autre, aucun titre n'est coupe, aucune forme ne sort de la slide, aucun engagement
ne deborde de sa case de mois, aucun trait ne touche un engagement, deux
engagements du meme mois sont empiles, et chaque jalon porte sa coche.

## 3. Ce que la frise n'a pas le droit de perdre

Un document qui part en comite ne peut pas taire ce que les trois blocs
disaient :

- **Un jalon qui ne tient aucun engagement** garde sa boite : celle de son theme,
  datee du milieu de son trimestre, la seule date que la donnee porte.
- **Un jalon sans theme** n'est pas efface : sa boite n'a pas de titre. Ces jalons
  ne forment pas une categorie « sans theme », ils sont ceux qui n'en ont pas.
- **Un engagement sans date** n'a pas de place sur l'axe : il est cite sous la
  frise, et la boite de ses jalons est datee du trimestre de son premier jalon.
- **Un jalon qui tient deux engagements** est dans les deux boites : ce sont deux
  promesses distinctes, et taire l'une reviendrait a dire qu'elle n'existe pas.
  Dans une meme boite, il n'apparait qu'une fois.
- **Le statut d'un jalon** est une coche posee **a droite** de son titre, et elle
  dit ses trois etats par le dessin autant que par la couleur : **fait** = pastille
  pleine et cochee, **en cours** (y compris a risque ou bloque) = anneau avec un
  point au centre, **pas commence** = anneau vide. Deux anneaux identiques ne
  distinguaient pas ce qui avance de ce qui dort, et une couleur seule ne se lit
  pas une fois la slide projetee. Elle mesure 0,15 pouce : a 0,10 elle faisait
  deux millimetres et passait pour absente. A gauche, elle decalait chaque titre
  de sa largeur, et un oeil qui descend une liste lit des titres alignes.
- **La dependance d'un jalon** est souvent la seule ligne qui explique un
  glissement. Elle reste en HTML, qui n'a pas de bas de page a tenir, sur sa
  propre ligne pour ne pas noyer le titre. Elle n'est pas sur la slide : le
  document des dependances existe pour elle.
- **La phase d'un jalon, EA ou GA**, suit son titre, en encre de service et non
  aux couleurs de la phase : la coche porte deja une couleur, celle du statut, et
  deux codes couleur sur une ligne ne se distinguent plus de loin. Les deux
  lettres ont leur legende au bas de la slide.

## 4. Le titre d'une boite

Une boite doit dire de quoi elle parle : elle est rangee dans l'ordre des dates
et non sous l'etoile de son engagement, donc son trait seul dirait « cette
date-la » sans dire « cette promesse-la ».

Son titre est donc **l'engagement que ses jalons tiennent**. Pour les jalons qui
n'en tiennent aucun, c'est leur **theme** : l'initiative qu'ils servent, ou a
defaut le theme libre que leur squad leader a saisi
(`reportcommon.milestone_theme`). Les deux repondent a la meme question, et un
squad leader utilise l'un ou l'autre selon que le sujet a ete porte au rang
d'initiative ou non.

L'objectif annuel, lui, garde son seul vrai role : etre un objectif qu'on suit,
dont la page de synthese compte les rouges. Il n'apparait pas sur cette frise.

## 5. Un engagement est une date, pas une duree

Le repere est une **etoile posee sur le mois**, et le titre s'ecrit a cote. Il a
d'abord ete dessine comme une pastille pleine occupant plusieurs mois, pour loger
ce titre : une forme qui s'etire se lit comme une periode, elle disait « de
septembre a novembre » la ou la donnee dit « le 30 septembre ». La largeur est un
besoin de mise en page, jamais une information.

L'etoile est **dessinee**, en SVG a l'ecran (`reportcommon.otd_star_svg`) et en
forme PowerPoint dans le deck, pour la meme raison que le nuage du moral : un
caractere « etoile » depend de la police installee sur le poste qui ouvre le
document et sort en carre la ou elle manque.

Les deux portees se distinguent par la couleur, la meme partout : bleu de marque
pour l'engagement du management, cyan profond pour celui que la squad prend
elle-meme, avec leur legende sous la frise parce qu'une couleur sans legende se
devine, mal, en reunion. Un engagement sans jalon garde son etoile et son titre :
c'est la promesse la plus fragile du lot, puisque rien n'est encore pose pour la
tenir.

En HTML, la page s'elargit avec le nombre de boites : a onze boites sur 920
pixels, chacune en ferait soixante et le texte casserait tous les cinq
caracteres. La frise defile alors horizontalement, et le JPG est rendu a la
largeur reelle de la page, donc il montre tout.

## 6. Le moral de l'equipe

Chaque document porte le moral declare par la squad, en haut a droite : **« Team »
au-dessus, « Mood » en dessous, et le nuage a droite**. Vert quand ça va bien,
ambre quand c'est moyen, rouge quand ça ne va pas, avec la date rangee en petit
dans le coin de la slide. Elle date le moral, elle ne le dit pas : sous le nuage,
sur une troisieme ligne centree, elle prenait le meme rang que le niveau, qui est
la seule chose a lire de loin.

Le niveau n'est plus ecrit en toutes lettres a cote du nuage : il se lit sur le
visage et sur la couleur, et l'ecrire revenait a le dire deux fois dans deux
centimetres. Quand rien n'est declare, il n'y a pas de nuage et « non renseigne »
prend sa place.

Le nuage est **plein** et non pastel : pose en haut d'une slide a cote d'un
bandeau navy, une teinte claire cernee d'un filet fin disparaissait.

**Un nuage dessine, pas un emoji.** Un emoji depend de la police installee sur le
poste qui ouvre le document : il change de style d'un support a l'autre et sort en
carre la ou le jeu couleur manque. Le nuage est dessine, donc il sort partout
pareil.

Il est surtout **decrit une seule fois**, dans un repere de 64 x 46, et les deux
supports lisent cette description : le contour (`MOOD_CLOUD_D`), les deux yeux
(`MOOD_CLOUD_EYES`) et les trois bouches (`MOOD_CLOUD_MOUTH`). L'ecran et l'export
HTML les rendent en arcs et en courbes SVG (`reportcommon.mood_cloud_svg`, repris a
l'identique par `MoodCloud` cote interface) ; la slide, qui ne connait que des
segments, les rend en polygones echantillonnes sur ces memes arcs
(`mood_cloud_outline`, `mood_cloud_mouth_points`). Le deck prenait auparavant la
forme « nuage » de PowerPoint : meme couleur, d'autres bosses, donc **une autre
icone que celle de l'application**, ce qui est exactement ce qu'un logo ne peut pas
se permettre. La bouche redit le niveau que la couleur donne, pour qui imprime en
noir et blanc.

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
sur les cartes du tableau de bord. Recliquer sur le niveau courant retire la
declaration, ce qui est la seule facon de dire « je ne me prononce plus » sans
inventer un quatrieme niveau, et efface aussi la date, sinon une date resterait a
l'ecran sans rien dater.

Quand rien n'est declare, les documents ecrivent « non renseigne » sans nuage :
un nuage gris se lirait comme un quatrieme niveau, alors que « non renseigne »
n'en est pas un.

Le meme dessin sert partout, a l'ecran comme dans les documents
(`reportcommon.mood_cloud_svg`, `MoodCloud`, et les formes du deck) : le moral se
reconnait d'un support a l'autre.

## 7. Les trois formats

| Format | Ce qui le produit | Remarque |
|---|---|---|
| HTML | `report.render_html` -> `_timeline_html` | Feuille de style embarquee, pour ne dependre d'aucun build |
| JPG | Le navigateur, a partir de ce meme HTML | `ExportMenu.renderHtmlToJpg`, donc rien a maintenir a part le HTML |
| PPTX | `reportpptx.render_pptx` -> `squad_slide` | Une squad, une slide, 13,33 x 7,5 pouces |

Le deck suit le modele fourni : bandeau de titre avec le responsable, moral en
haut a droite, la grande carte de la frise, puis les messages cles et le budget
en bas. Un export de plusieurs squads garde sa page de synthese en tete ; un
export d'une seule squad est le meme deck sans elle.

### Lisible depuis le fond de la salle

Un deck se projette. Les corps de texte de la slide d'une squad sont donc donnes
pour une lecture a distance (jusqu'a 11,5 pt pour un titre de jalon, 9 pt pour un
engagement, 11 pt pour les mois, 13 pt pour un trimestre, 10 pt pour les messages
cles et le budget), et l'encre est un noir
presque franc (`#111827`) : sur un videoprojecteur fatigue, un gris anthracite
perd la moitie de son contraste et le texte se devine au lieu de se lire.

La coche d'un jalon porte son statut, et elle a sa **legende en bas de slide** :
une couleur sans legende se devine, et se devine mal quand on decouvre le
document en reunion. Cette legende est en 10 pt et **ne revient jamais a la
ligne** : en 7 pt sur une largeur estimee trop courte, le libelle se coupait en
deux et sa seconde ligne tombait hors de la slide, ce qui donnait une frise sans
legende sur les modeles dont la police est large.

## 7 bis. Le corps du texte des diapositives

Un deck se lit projete au fond d'une salle, pas a 40 cm d'un ecran. Les corps
d'origine etaient cales sur la seconde lecture et passaient trop petits en
comite. Un facteur unique, `pptxtpl.FONT_SCALE`, les agrandit, et il est applique
au seul endroit ou un nombre devient une taille de police, dans les trois
renderers (rapport, one-pager Steerco, organigramme).

Ce qui se deduit d'un corps passe par le meme facteur : hauteur d'une ligne,
nombre de caracteres par ligne, largeur d'une pastille. Sans cela le texte
grossirait dans des boites restees a l'ancienne mesure, et en sortirait.

La ou une mise en page **choisit** son corps, elle part simplement de plus haut :
la frise et les cartes par trimestre descendent une echelle de tailles jusqu'a ce
que tout tienne, donc elles retombent d'elles-memes sur l'ancien corps quand la
place manque. Agrandir ne peut pas faire disparaitre une boite, et
`test_no_box_is_dropped_at_this_density` le verifie a pleine charge.

Trois endroits restent **hors du facteur**, et pour la meme raison : leur taille
est dictee par la place disponible, pas par le confort de lecture, et les
agrandir ne donnerait rien a lire de plus.

- Le nom d'une squad dans la vue par trimestre, couche dans la hauteur de sa bande.
- Le texte d'une carte de l'organigramme, calibre sur la largeur de la carte, qui
  descend elle-meme jusqu'a ce que le mot le plus long rentre (voir plus bas).
- La legende du bas de slide, qui prend le corps commun **tant que sa rangee tient
  dans la largeur de la diapositive** et redescend sinon : les libelles n'ont pas
  la meme longueur en francais et en anglais, c'est donc la somme qui decide.

Trois debordements que l'agrandissement a rendus visibles ont ete corriges plutot
que contournes. La barre d'avancement d'un trimestre etait posee a une distance
fixe du haut de sa carte, calee sur un corps de 13 points : la ligne de titre
descendant plus bas, « Q4  50 % » s'ecrivait par-dessus sa propre barre. La
hauteur de la carte et la position de la barre se deduisent maintenant du corps
reel (`test_a_quarter_title_never_sits_on_its_own_progress_bar`).

**L'organigramme**, lui, cassait sur la largeur de l'arbre et non sur le corps du
texte. La largeur d'une carte avait un plancher d'un pouce et dix : a quatorze
squads, un emplacement n'en fait plus que neuf, et chaque carte mordait sur sa
voisine. Elle ne depasse plus son emplacement. Et comme PowerPoint passe un titre
a la ligne mais **ne coupe pas un mot**, « Management » sortait de sa carte des
deux cotes : le corps descend jusqu'a ce que le mot le plus long rentre, et le mot
est coupe en dernier ressort. Les trois regles ont leur test dans
`backend/tests/test_org_export.py`, sur l'arbre du jeu de demonstration, qui est
large. La carte du budget etait plus courte que son contenu et
« Prevision » sortait par le bas depuis toujours : elle a desormais la hauteur de
son titre et de ses trois lignes, prise sur la frise qui en avait de reste
(`test_the_bottom_cards_are_tall_enough_for_their_own_text`). Et l'axe est
desormais **decoupe par trimestre dans les deux bandes** : un trimestre et ses
trois mois forment un bloc, janvier, fevrier et mars ensemble sous Q1, separe du
suivant par la meme gouttiere en haut comme en bas. La carte prenait sa gouttiere
entierement a droite, donc Q1 s'arretait avant la fin de mars; et la bande des
mois etait d'un seul tenant sous des cartes separees, donc rien n'y disait ou un
trimestre finissait. Tout ce qui se pose sur un mois (l'etoile d'un engagement,
le trait d'une boite, la largeur d'une case) suit cette grille, donc rien ne se
decale (`test_a_quarter_card_covers_exactly_its_three_months`).

## 8. La frise a pleine charge

Une mise en page ne casse pas sur un cas, elle casse quand tout arrive ensemble.
Le jeu de donnees de demonstration (`app.seed_fake`) sert donc aussi de cas de
charge : neuf jalons par squad tires d'un catalogue de titres de longueurs
variees, un trimestre qui en porte parfois trois, plusieurs themes par squad, des
jalons sans theme, et cinq engagements par squad dont deux le meme mois et
certains en novembre et en decembre.

Il a longtemps porte cinq jalons de titre court, jamais plus de deux par
trimestre, aucun objectif rattache a une initiative, et **aucun engagement** : la
bande du haut ne se dessinait jamais et la frise n'avait qu'une ligne quel que
soit le nombre de jalons. Une mise en page se validait alors sans avoir rien eu a
ranger. `backend/tests/test_export_timeline_dense.py` tient les deux bouts : que
ce jeu reste dense, puis qu'a cette densite les sept regles de la section 2
tiennent, sur les treize slides.

## 9. Ou est le code

| Role | Fichier |
|---|---|
| Les boites, leur titre et leur date, l'etoile | `backend/app/reportcommon.py` (`timeline_groups`, `milestone_theme`, `otd_star_svg`) |
| La frise en HTML et sa feuille de style | `backend/app/report.py` (`_timeline_html`, `_grid_width`, `_TIMELINE_CSS`) |
| La slide d'une squad | `backend/app/reportpptx.py` (`squad_slide`) |
| Le JPG, rendu depuis le HTML | `frontend/src/components/ExportMenu.tsx` |
| Declarer le moral | `frontend/src/components/TeamMood.tsx`, `PUT /api/squads/{id}/mood` |
| Le corps du texte des decks | `backend/app/pptxtpl.py` (`FONT_SCALE`, `font_size`) |
| L'organigramme exporte | `backend/app/orgrender.py` (`fit_size`, `fit_text`) |
| Le jeu de donnees de demonstration | `backend/app/seed_fake.py` |
| Tests | `backend/tests/test_export_timeline.py`, `backend/tests/test_export_timeline_dense.py`, `backend/tests/test_org_export.py`, `backend/tests/test_mood.py` |
