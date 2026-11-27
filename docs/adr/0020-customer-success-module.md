# 0020. Customer Success, un module à part pour suivre les projets livrés

- Statut : Accepted
- Date : 2026-11-27
- S'inspire de : [0018](0018-steerco-is-a-topic-of-its-own.md), [0019](0019-steerco-contributors.md)

## Contexte

La lead Customer Success suit ses projets dans OneNote et dans des mails récapitulatifs.
Rien dans l'application ne les porte : ce ne sont ni des OTD, ni des initiatives de
squad, ni des plateformes Steerco. Le suivi a besoin d'une chronologie datée, de
blocages visibles et d'un récap à diffuser.

## Décision

1. Un module `customer_success`, désactivé par défaut, avec son propre menu
   « Customer Success ».
2. Cloisonné **par tribe**. Les droits suivent le modèle du Steerco : **responsable CS**
   désigné (le tribe leader l'est par défaut), **contributeur CS** nommé projet par
   projet, **lecteurs** par une capacité de persona.
3. Des **projets à plat** : client et personnes en texte libre (l'offre, présente en 4.2.0, a été retirée ensuite), sans fiches
   liées. Les étapes sont paramétrables.
4. Une seule source par information : les décisions sont dans le journal, et le
   blocage affiché comme la prochaine action se déduisent des **points à suivre**.
5. Le récap réutilise le mécanisme des diffusions et le Studio, et n'a pas de canal
   d'envoi à lui.

## Conséquences

- Pas de dédoublonnage des personnes : « Benoit Huyot » et « Benoît Huyot » restent
  deux textes. C'est le prix d'une saisie aussi rapide que OneNote.
- Aucun document n'est stocké, seulement des liens : pas de rétention à gérer, et pas
  de données C2 dans la base au-delà du texte saisi.
- Pas de notifications : le tableau de bord porte les retards, les fins d'accès et les
  projets sans nouvelles.
