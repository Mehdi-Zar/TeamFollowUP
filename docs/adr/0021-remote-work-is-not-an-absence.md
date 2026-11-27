# 0021. Le télétravail n'est pas une absence : une vue « Sur site / À distance »

- Statut : Accepted
- Date : 2026-11-27

## Contexte

Un leader veut savoir, jour par jour, qui de son équipe est sur site et qui travaille à
distance, et avoir un récapitulatif pour toute l'équipe. Le télétravail a déjà été un
type de congé (migration 0019), retiré en 0020 : rangé parmi les absences, il gonflait
le nombre d'absents, passait par la validation et faisait déclarer chaque jour à la main,
alors que la plupart des gens ont des jours fixes.

## Décision

1. Le télétravail est **séparé des congés** : deux tables, `remote_patterns` (la
   **semaine habituelle** d'une personne : les jours où elle travaille d'habitude à
   distance) et `remote_days` (un **changement pour un jour** : à distance un jour
   habituellement sur site, ou l'inverse). Pas de validation.
2. Le statut d'un jour se calcule dans `app/presence.py`, de la règle la plus forte à la
   plus faible : samedi et dimanche ne comptent pas ; une absence en cours (en attente ou
   validée) l'emporte ; puis le changement du jour ; puis la semaine habituelle ; sinon
   sur site.
3. **Journées entières seulement**, comme la plupart des accords de télétravail.
4. Une **vue à part** dans le menu Congés, « Sur site / À distance » : un récapitulatif
   (totaux de la période, chaque jour avec qui est où, chaque squad), puis la grille de
   l'équipe, où un clic sur un jour bascule entre sur site et à distance. Semaine ou mois.
5. **Qui voit** : comme les absences, toute la tribe (l'administrateur : toutes).
   **Qui change** : la personne elle-même, et ceux qui gèrent ses congés (son squad
   leader, son tribe leader, l'administrateur).
6. Une option du module Congés, `leaves.remote`, allumée par défaut, l'éteint.

## Conséquences

- Les nombres du récapitulatif comptent des jours-personnes : une personne sur site trois
  jours compte trois.
- Une personne sans semaine habituelle est sur site tous les jours : la vue est juste
  dès le premier jour, et chacun ne règle que ses jours à distance.
- Supprimer un compte supprime sa semaine et ses jours (`userpurge`), et l'effacement des
  données « Congés » les emporte aussi (`datareset`).
- API : `GET /api/presence`, `PUT /api/presence/week/{user_id}`,
  `PUT /api/presence/day/{user_id}`.
