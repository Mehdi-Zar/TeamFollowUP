# ADR 0018 - Le Steerco est un sujet a part, gere par des Steerco leaders

Statut : accepte (version 4.0.0). Remplace la partie "qui remplit quoi" de
l'[ADR 0014](0014-platform-is-the-steerco-reporting-unit.md) : la plateforme reste
l'unite de reporting, mais la propriete par element disparait.

## Contexte

Jusqu'a la 3.x, le Steerco etait eparpille sur quatre ecrans : le parametrage dans
Administration > Plateformes, la saisie dans une etape de la Saisie hebdomadaire,
la consolidation dans un onglet du Dashboard (et son miroir dans Initiatives),
l'import Excel dans Administration. Les droits se deduisaient du role et des
squads : chaque carte KPI ou colonne SLA appartenait a une squad, qui seule
pouvait la remplir.

En pratique, la diapositive du comite est preparee par une ou deux personnes de
la tribu (le tribe leader, un PMO), qui collectent les chiffres. Le modele "chaque
squad remplit sa part" imposait d'attribuer chaque element, de relancer chaque
squad, et dispersait l'outil sur des ecrans dont ce n'etait pas le sujet.

## Decision

1. **Un menu "Steerco" de premier niveau**, une seule page a onglets : Saisie,
   Consolidation et export, Plateformes, Steerco leaders. Plus d'etape Steerco
   dans la Saisie hebdomadaire, plus d'onglet Steerco dans le Dashboard, Initiatives,
   Mes squads ni l'Administration. Le module `steerco` continue d'eteindre le tout.
2. **Steerco leader est une designation, pas un persona.** Table
   `steerco_leaders (user_id, tribe_id)` : on la cumule avec n'importe quel role
   (un squad leader peut etre Steerco leader). Un utilisateur peut l'etre sur
   plusieurs tribus.
3. **Qui gere** (tout faire sur les plateformes d'une tribu) : l'admin partout ;
   le tribe leader sur sa tribu, **par defaut** (une ligne de designation creee
   pour lui, que seul l'admin peut retirer) ; les Steerco leaders designes.
4. **Seuls ceux qui gerent saisissent.** La propriete par element
   (`owner_squad_id`, `merge_owned`, "contributeurs en retard") disparait. Le suivi
   devient un etat par plateforme et par mois. Deux Steerco leaders sur la meme
   plateforme sont departages par un controle de version : un enregistrement fait
   sur une version perimee est refuse (409) au lieu d'ecraser.
5. **Squads concernees** : le lien plateforme / squads devient facultatif et ne
   sert plus qu'a "Reprendre du reporting" (messages cles) et au lien de la page
   Squad.
6. **Consulter sans gerer** : capacite de persona `steerco` (Administration >
   Personas), **fermee par defaut**. Un lecteur ne voit que Consolidation et export.
7. **Designation** : onglet "Steerco leaders" du menu Steerco ; seuls l'admin et le
   tribe leader designent ; un Steerco leader n'en designe pas d'autre. Audite.
8. **Saisie** : un tableau plateformes x mois de l'annee ; un clic ouvre
   l'assistant en 5 etapes (inchange), qui offre "Reprendre le mois precedent"
   (valeurs de M-1, sans les evenements). L'import Excel est dans le meme onglet,
   ouvert aux Steerco leaders.
9. **Apparence** : le Studio des exports reste le seul moteur de mise en page ;
   `exportstore.can_design` reconnait le Steerco leader sur le perimetre
   `platform` des plateformes de sa tribu, et seulement celui-la.
10. **Cycle de vie d'un mois** : Brouillon, Valide (lecture seule), Rouvrir avec un
    motif obligatoire (audite, l'export du mois porte "Revise le ..."). L'import ne
    touche pas un mois valide et le signale.
11. **Mails** : relance mensuelle aux Steerco leaders (jour reglable, 5 par defaut,
    seulement s'il reste des plateformes non validees) et diffusion manuelle du
    pack du mois a une liste de destinataires, possible seulement quand toutes les
    plateformes du pack sont validees. Audite.
12. **Bascule** : les gabarits perdent leurs proprietaires, les contributrices
    deviennent les squads concernees, chaque tribe leader est designe sur sa
    tribu, tous les mois existants passent en Brouillon. Version majeure 4.0.0
    (routes retirees ou deplacees).

## Consequences

- Un seul endroit pour le sujet ; la Saisie hebdomadaire redevient le reporting de
  squad, sans etape mensuelle a part.
- La charge de collecte est assumee par les Steerco leaders, qui disposent de la
  duplication de M-1 et de l'import Excel pour la reduire.
- Le contrat d'API change : `/api/admin/import-steerco*` passe sous
  `/api/steerco/import*` ; `squads.steerco_enabled` n'est plus expose.
- Un mois valide ne bouge plus sans trace : le document presente au comite reste
  ce que le comite a vu, ou dit qu'il a ete revise.
