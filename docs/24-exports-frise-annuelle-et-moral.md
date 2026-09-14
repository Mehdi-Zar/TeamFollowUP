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

1. **Les trimestres**, avec l'avancement calcule de chacun et son commentaire.
2. **Les mois**, qui donnent la resolution de l'axe.
3. **Les engagements OTD**, poses a leur date juste sous les trimestres : c'est
   la promesse tenue ou non que le comite regarde en premier. Tous de la meme
   couleur, celle de la marque : une rangee d'engagements de quatre teintes ne
   laisse plus ressortir les jalons en dessous, dont la couleur dit un risque. Le
   statut reste ecrit, ce qui se lit aussi en noir et blanc.
4. **Une ligne par initiative**, portant **les jalons qui la servent**, chacun
   dans son trimestre.

La donnee ne change pas, seul son agencement change : le chainage existait deja
en base, une initiative porte des objectifs et un objectif porte des jalons
(`Initiative` <- `Objective.initiative_id` <- `RoadmapItem.objective_id`). Les
exports se contentent de le suivre.

### Ce que la frise n'a pas le droit de perdre

Un document qui part en comite ne peut pas taire ce que les trois blocs
disaient. Trois cas sont traites explicitement, et chacun a son test :

- **Un jalon qui ne sert aucune initiative** garde sa ligne, « Jalons hors
  initiative », plutot que de disparaitre. Un jalon absent d'un export se lit
  comme un jalon qui n'existe pas. Il en va de meme d'un jalon rattache a une
  initiative portee par une autre squad.
- **Un engagement sans date** n'a pas de place sur l'axe : il est cite sous la
  bande.
- **L'owner d'une initiative, l'echeance, la dependance d'un jalon** suivent sur
  la ligne. La dependance est souvent la seule ligne qui explique un glissement.

### Un engagement est une date, pas une duree

Le repere est un losange pose sur le mois, et le titre s'ecrit a cote. Il a
d'abord ete dessine comme une pastille pleine occupant plusieurs mois, pour loger
ce titre : une forme qui s'etire se lit comme une periode, elle disait « de
septembre a novembre » la ou la donnee dit « le 30 septembre ». La largeur etait
un besoin de mise en page, jamais une information.

### Deux engagements qui se genent

La place reservee au titre suit sa longueur, exprimee en mois. Quand deux se
recouvrent, le second descend d'une bande. En HTML le nombre de bandes n'est pas
limite ; sur une slide il l'est a trois, parce que la hauteur d'une slide ne
s'etire pas, et ce qui ne tient pas est compte et affiche (`+2`) plutot que
supprime.

Le calcul est le meme pour les deux formats (`reportcommon.pack_otds`) : deux
mises en page qui se contrediraient sur la place d'un engagement seraient pires
qu'une seule imparfaite. Seule la densite de texte change, huit caracteres par
mois en HTML, seize sur une slide.

## 2. Le moral de l'equipe

Chaque document porte le moral declare par la squad, en haut a droite : 😀 ça va
bien, 😐 moyen, 🙁 ça ne va pas, avec la date de la declaration.

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

Quand rien n'est declare, les documents ecrivent « non renseigne » sans visage :
un point d'interrogation se lirait comme un quatrieme niveau.

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

## 4. Ou est le code

| Role | Fichier |
|---|---|
| Le regroupement des jalons par initiative, le rangement des engagements | `backend/app/reportcommon.py` (`timeline_rows`, `pack_otds`) |
| La frise en HTML et sa feuille de style | `backend/app/report.py` (`_timeline_html`, `_TIMELINE_CSS`) |
| La slide d'une squad | `backend/app/reportpptx.py` (`squad_slide`) |
| Le JPG, rendu depuis le HTML | `frontend/src/components/ExportMenu.tsx` |
| Declarer le moral | `frontend/src/components/TeamMood.tsx`, `PUT /api/squads/{id}/mood` |
| Tests | `backend/tests/test_export_timeline.py`, `backend/tests/test_mood.py` |
