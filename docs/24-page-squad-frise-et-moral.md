# 24 - Page d'une squad : la frise annuelle et le moral d'equipe

Deux changements sur la page d'une squad : le moral en haut a droite, et **un seul
bloc** la ou il y en avait trois.

## 1. Un bloc au lieu de trois

La page empilait trois cartes : les initiatives, les OTD, puis une roadmap
decoupee en quatre colonnes de trimestre. Trois lectures pour une seule question,
« ou en est l'annee », et aucune des trois ne disait a quoi servait un jalon ni
quand tombait un engagement.

Le bloc unique pose tout sur **le meme axe**, parce que le temps est la seule chose
que ces trois objets ont en commun :

1. **Les trimestres**, avec l'avancement calcule de chacun et son commentaire.
2. **Les mois**, qui donnent la resolution de l'axe.
3. **Les engagements OTD**, poses a leur date, en gros, juste sous les trimestres :
   c'est la promesse tenue ou non que le comite regarde en premier. La couleur suit
   leur statut (a l'heure, a risque, en retard, livre).
4. **Une ligne par initiative**, et dans chaque ligne **les jalons qui la servent**,
   places dans leur trimestre. Les jalons qui ne repondent a aucune initiative ont
   leur propre ligne, plutot que d'etre caches.

La donnee ne change pas, seul son agencement change : le chainage existait deja,
une initiative porte des objectifs, un objectif porte des jalons
(`Initiative` <- `Objective.initiative_id` <- `RoadmapItem.objective_id`).

La grille fait treize colonnes : une pour le libelle, douze pour les mois, et un
trimestre en occupe trois. C'est la grille qui tient l'alignement, pas des
pourcentages calcules a la main.

Les engagements OTD viennent d'un appel a part (`/api/otds`) parce qu'ils vivent au
niveau de la tribu. L'API ne renvoie que ce que le lecteur a le droit de voir :
pour un membre, la bande est vide, ce qui est une reponse et non une erreur.

## 2. Le moral de l'equipe

Trois niveaux, en haut a droite : 😀 ça va bien, 😐 moyen, 🙁 ça ne va pas.

**Trois et pas cinq.** Une echelle fine invite a la nuance, or ce qu'on cherche ici
est un signal. Trois choix se decident en une seconde, ce qui est la condition pour
que la case soit remplie chaque semaine plutot qu'une fois en janvier.

**La date compte autant que le niveau.** Un moral de mars affiche en septembre ment
plus surement qu'une case vide : l'age est toujours indique, et au-dela de 45 jours
il est signale comme a rafraichir. Retirer la declaration efface aussi la date,
sinon une date resterait a l'ecran sans rien dater.

**Qui le declare.** Qui peut editer la squad : son responsable, ses
co-responsables, son tribe leader, un admin. C'est le moral de SON equipe, pas une
note qu'un tiers lui attribue. Recliquer sur le niveau courant retire la
declaration, ce qui est la seule facon de dire « je ne me prononce plus » sans
inventer un quatrieme niveau. Un commentaire facultatif de 300 caracteres
accompagne le niveau.

Le moral apparait aussi, en petit, sur chaque carte du tableau de bord : c'est la
seule donnee de cette grille qu'aucun calcul ne produit, et celle qui explique
souvent les autres.

## 3. Ou est le code

| Role | Fichier |
|---|---|
| La frise (trimestres, OTD, initiatives et jalons) | `frontend/src/components/RoadmapTimeline.tsx` |
| Le moral, et sa version compacte pour la grille | `frontend/src/components/TeamMood.tsx` |
| Colonnes `mood`, `mood_at`, `mood_comment` | `backend/alembic/versions/0032_squad_mood.py` |
| `PUT /api/squads/{id}/mood` | `backend/app/routers/squads.py` |
| Styles de la frise et du moral | `frontend/src/theme.css` |
| Tests | `backend/tests/test_mood.py` |
