# ADR 0014 - La plateforme est l'unite de reporting du Steerco

Statut : accepte. Remplace le choix implicite de l'ADR d'origine du module Steerco,
ou l'unite etait la squad.

## Contexte

Le comite de pilotage regarde une diapositive **par plateforme**. Or une plateforme
n'est pas toujours servie par une seule squad : TP-S3NS est alimentee par Managed
Services et TP-S3NS LZ, tandis que TDP et Castle ont une source unique.

Le modele initial stockait un instantane par `(squad, mois)` et produisait une
diapositive par squad. Une plateforme a deux squads donnait donc deux diapositives,
et rien dans le modele ne savait qu'elles parlaient de la meme chose.

## Options examinees

1. **Fusionner au rendu.** Declarer des plateformes, regrouper les squads, et
   fusionner les agregats au moment de produire la diapositive. Rapide, mais la
   fusion est ambigue : deux squads qui renseignent la meme colonne SLA laissent le
   rendu arbitrer entre deux valeurs, et le chiffre affiche n'a plus d'auteur.
2. **La plateforme devient l'unite, avec attribution par element.** La plateforme
   porte le **gabarit** de sa diapositive et attribue chaque carte KPI et chaque
   colonne SLA a une squad contributrice.
3. **Hybride.** Les instantanes restent par squad, la plateforme declare seulement
   d'ou vient chaque champ. Evite la migration mais entretient deux notions de
   gabarit.

## Decision

Option 2. `steerco_entries` est desormais unique sur `(platform, period)`, et
`platforms.template` attribue chaque element a une squad contributrice.

Une ecriture ne retient du payload que les elements dont l'appelant est proprietaire
(`app/platforms.py:merge_owned`). Deux squad leaders peuvent donc remplir la meme
diapositive en meme temps sans jamais s'ecraser : **un chiffre, un auteur, aucune
fusion**. Les evenements sont la seule section partagee, et chaque ligne porte sa
squad d'origine, ce qui donne la meme garantie a l'echelle de la ligne.

## Consequences

- La **forme de l'instantane est inchangee** (`data["kpis"][i]`, `data["sla"]`, ...),
  seule sa cle change. Les 600 lignes de rendu HTML et PPTX n'ont pas bouge.
- Les libelles ne viennent plus du formulaire mais du gabarit : un onglet reste
  ouvert ne peut plus renommer une ligne de la diapositive.
- `squads.steerco_enabled` devient **derive** de l'appartenance a une plateforme
  (`sync_squad_flags`), et n'est plus modifiable a la main. L'activation en
  libre-service par le squad leader disparait : declarer une plateforme et attribuer
  ses elements est une decision de tribe leader.
- Un element sans proprietaire n'est le travail de personne. Il reste modifiable par
  le tribe leader et est compte comme "non attribue" dans l'ecran d'administration,
  plutot que de rester vide en silence tous les mois.
- La migration `0029_platforms` transforme chaque squad qui faisait du Steerco en une
  plateforme d'une seule contributrice : a l'arrivee, rien ne change a l'ecran pour
  elles. Regrouper deux squads sous une plateforme est ensuite un geste volontaire.
- Le `downgrade` ne peut pas rendre a chaque squad ce qu'une plateforme partagee a
  fusionne : la ligne revient a sa premiere contributrice. C'est le prix du
  regroupement, et il est documente dans la migration.
