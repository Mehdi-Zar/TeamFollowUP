# ADR 0015 - Un engagement OTD a deux portees, et deux liens vers les jalons

Statut : accepte. Complete l'ADR 0007 (statuts derives) et le modele de reporting
de l'ADR d'origine des OTD, ou l'engagement etait un objet du tribe leader.

## Contexte

Un OTD etait, par construction, l'engagement du management : le tribe leader (ou
un admin) le creait, le datait et y rattachait les jalons. Un squad leader qui
prenait un engagement date devant sa propre squad n'avait nulle part ou l'ecrire.
En pratique il le mettait dans un intitule de jalon ou dans un message cle, c'est
a dire dans un endroit d'ou aucun rapport ne sait le relire comme un engagement :
ni date d'engagement, ni statut derive, ni ligne dans la frise.

La demande est double : que le squad leader puisse ajouter ses propres engagements,
et que les documents distinguent visuellement les deux origines.

## Options examinees

1. **Un drapeau booleen `is_squad_otd`.** Le plus court a ecrire. Mais un booleen
   ne dit pas qui possede l'objet, et chaque garde aurait du le retraduire en
   regle d'acces; ajouter une troisieme origine un jour aurait demande un second
   booleen et leur combinaison.
2. **Une table separee `squad_otds`.** Isolation nette des droits, mais duplication
   complete : memes colonnes, meme statut derive, meme rattachement aux jalons, et
   un rapport qui doit les montrer cote a cote les aurait refusionnees a la
   lecture, avec deux chemins a maintenir pour un seul concept.
3. **Une portee sur l'objet existant** (`scope` valant `management` ou `squad`,
   plus `squad_id`), la portee decidant qui a le droit d'ecrire.

## Decision

L'option 3. Un engagement reste un engagement : meme table, meme statut derive,
meme facon de grouper des jalons. `scope` dit qui le possede, et c'est de lui que
decoule le controle d'acces (`routers/otds.py:_assert_can_write`).

Deux consequences que la decision assume :

- **La portee est fixee a la creation.** Elle n'est pas dans `OtdUpdate`. Un squad
  leader capable de basculer son engagement en `management` s'attribuerait un
  droit d'ecriture sur un objet du tribe leader.
- **Le tribe leader lit un engagement de squad sans pouvoir l'ecrire.** C'est ce
  qui en fait l'engagement de la squad. Il le voit dans ses rapports, ou il figure
  a cote des siens.

## Deux liens vers les jalons, et non un seul

`roadmap_items.otd_id` porte le rattachement de l'engagement management;
`squad_otd_id` celui de la squad. Un lien unique aurait oblige a choisir, alors
que le meme jalon tient en general les deux promesses : le dernier qui rattache
aurait defait le travail de l'autre, sans le lui dire et sans trace a l'ecran.

Le cout est une colonne nullable de plus et une ligne de plus dans la migration.
Le benefice est que chaque proprietaire ecrit sa propre colonne, donc aucune des
deux operations ne peut annuler l'autre.

## Consequences

- Migration `0035_otd_scope` : `otds.scope` (defaut `management`, ce que sont les
  lignes existantes par definition), `otds.squad_id`, `roadmap_items.squad_otd_id`.
  Le retour arriere supprime les engagements de squad plutot que de les faire
  passer pour des engagements du management, ce qui serait un contresens.
- La frise des exports fait une ligne par engagement (et non plus par initiative),
  avec une couleur par portee, la meme en HTML et en PPTX. Voir
  [24](../24-exports-frise-annuelle-et-moral.md).
- Un jalon qui tient les deux engagements apparait sous les deux lignes. C'est le
  meme travail lu par deux promesses, et le document le montre comme tel.
