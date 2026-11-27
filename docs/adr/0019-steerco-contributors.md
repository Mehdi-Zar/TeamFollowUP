# 0019. Des contributeurs Steerco, plateforme par plateforme

- Statut : Accepted
- Date : 2026-11-27
- Complete : [0018](0018-steerco-is-a-topic-of-its-own.md)

## Contexte

Depuis la 4.0 (ADR 0018), seuls les Steerco leaders remplissent les chiffres. Dans
une tribe, ces chiffres viennent souvent de plusieurs personnes : le responsable d'une
plateforme connait ses KPI, pas le PMO qui mene le Steerco. Les faire Steerco leaders
leur donnerait tout (valider, envoyer, voir toutes les plateformes, regler la tribe) ;
les laisser dehors oblige le Steerco leader a recopier ce qu'on lui envoie.

## Decision

1. **Un contributeur Steerco** est nomme **sur une plateforme**, par un Steerco leader
   de la tribe (ou l'administrateur), dans la fiche de la plateforme
   (`Parametrage > Les plateformes`). Table `steerco_contributors (user_id,
   platform_id)`, cumulable avec n'importe quel role et sur plusieurs plateformes.
2. Il **remplit le mois** de ses plateformes, a l'ecran ou par Excel, et rien d'autre :
   il ne valide pas, ne rouvre pas, n'envoie pas la presentation, ne voit pas le
   Parametrage, et ne voit **que ses plateformes** (pas celles des autres).
3. Il recoit le **rappel mensuel**, limite a ses plateformes non validees.
4. Le libelle est « contributeur **Steerco** », pour ne pas le confondre avec la
   persona Contributor des squads.

## Consequences

- La validation reste aux Steerco leaders : le mois que voit le comite est toujours
  relu par quelqu'un qui en repond.
- Les routes d'ecriture d'un mois (`PUT /api/steerco/platform/{id}`, historique,
  messages cles, apercu, import Excel) acceptent les Steerco leaders **et** les
  contributeurs de la plateforme ; les autres restent reservees aux Steerco leaders.
- `/api/auth/me/permissions` ajoute `steerco.contribute`,
  `contribute_platform_ids` et `contribute_tribe_ids`.
