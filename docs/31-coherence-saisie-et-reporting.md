# 31 - Coherence de la saisie et du reporting

Deux audits de l'experience (saisie, reporting, pages de squad, abonnements, droits)
ont releve 35 puis 34 incoherences. Le fil conducteur des corrections : **chaque
donnee a un endroit ou on la modifie**, et partout ailleurs on la lit, avec un lien
vers cet endroit qui ouvre la bonne squad, la bonne annee et la bonne etape.

| Donnee | Se modifie dans | Par qui |
|---|---|---|
| Jalons, OTD de la squad, messages cles, moral, valeurs des KPI, commentaire d'avancement, chiffres Steerco, soumission | Reporting (saisie) | leader, co-leaders, contributeurs, admin |
| Fiche de la squad, OTD, equipe, budget, comites | Mes squads | leader et co-leaders (leurs squads seulement), tribe leader, admin |
| Squad leader, co-leaders, contributeurs, ordre, options (KPI, budget), initiatives | Mes squads, et le tableau Administration > Squads | tribe leader, admin (le leader nomme aussi ses contributeurs) |
| Envois programmes et e-mail a chaque modification | Administration > Rapport | tribe leader (programme de sa tribe), admin |
| Abonnement personnel | fenetre « Abonnement au rapport » | chacun |

La page d'une squad lit tout cela et renvoie, section par section, vers l'endroit
ou la section se modifie.

## 1. Un seul engagement : l'OTD

Les objectifs de squad sont retires (decision du 25/09/2026) : plus de route
`/api/objectives`, plus d'interrupteur, plus rien dans les seeds, les soumissions,
la reponse `/api/squads/{id}` ni le mail de changements (qui compare desormais les
OTD). La table `objectives` reste pour les saisies deja figees qui la citent.

Un OTD du management peut porter une squad (`squad_id`). Toute la tribe lit tous ses
OTD, a l'ecran comme a l'API (`GET /api/otds`), puisque les exports les montrent
deja a chacun. L'ecriture reste fermee.

## 2. Diriger une squad est un role dans la squad, pas un persona

Quiconque est nomme leader ou co-leader d'une squad la dirige, quel que soit son
persona : un tribe leader nomme a la tete d'une squad la saisit et la soumet
(`deps.leads_squad`, `perms.leadsSquad`). La capacite « reporting » lui est ajoutee
d'office (`personasconfig.user_caps`). Un leader voit aussi la squad qu'il dirige
dans une autre tribe.

## 3. Le contributeur

Nouveau persona integre, `contributor`. Un contributeur est nomme **par squad**
(table `squad_contributors`, migration `0037`), par le tribe leader ou par le leader
de la squad, dans Mes squads ou dans Administration > Squads. Nommer un simple
membre lui donne le persona Contributeur.

Il remplit et soumet le reporting de ses squads (`deps.reports_for_squad`,
`deps.can_report`) : jalons, OTD de la squad, messages cles, moral, KPI, avancement,
Steerco. Il ne touche pas a la fiche, a l'equipe, au budget, aux comites ni aux
contributeurs, et n'epingle pas de message du fil.

## 4. Mes squads

- Le tribe leader et l'admin y voient toutes les squads, avec un selecteur d'annee
  (l'annee par defaut de l'instance) : Infos, Options, OTD et initiatives, Equipe,
  Budget, Comites. Supprimer une squad demande une confirmation.
- Le squad leader y voit **ses squads et elles seules** : Infos (nom, description,
  produits, materiel, contributeurs), ses OTD, Equipe, Budget, Comites.
- `/mes-squads?squad=12&step=otd` ouvre directement la fenetre sur la bonne etape.
- On ne rattache ici qu'une initiative libre : celle d'une autre squad apparait
  grisee avec son nom. Changer une initiative de squad se fait dans l'ecran des
  initiatives, qui previent que ses jalons de l'ancienne squad seront detaches.

## 5. La saisie dit ou l'on en est

- Chaque etape a un etat : a faire, fait, facultatif, modifie depuis la derniere
  soumission, inchange, a soumettre, a jour, **a rafraichir** (moral d'une autre
  semaine). Calcul : `GET /api/squads/{id}/snapshots/pending?year=`.
- Un bandeau signale les changements non soumis, ou une squad jamais soumise.
- La derniere etape se termine sur « Soumettre », sans « Suivant ».
- « Comparer », dans l'historique, porte sur les six sections soumises (jalons, OTD,
  messages, moral, avancement, KPI).
- Une saisie sans libelle prend la semaine ISO (`2026-W39`).

## 6. L'annee

Quand un appel ne precise pas l'annee, le serveur prend l'annee par defaut de
l'instance (`generalconfig.reference_year`), plus son horloge. Les liens vers une
squad portent l'annee de l'ecran d'ou l'on vient, et la saisie la lit.

## 7. Les e-mails

Administration > Rapport a deux cartes, chacune avec ses destinataires :

- **Rapport programme** : jours, heure, contenu, destinataires.
- **Un e-mail a chaque modification** (admin) : quelles modifications
  (« Toutes » / « Aucune »), pour quelles squads, qui recoit (adresses saisies,
  plus « + Tribe leader de la squad » et « + Squad leader et co-leaders », ajoutes
  par un bouton et listes avec les autres), a quel rythme, puis toute la regle en une
  phrase (« Quand une squad modifie : budget, moral, un e-mail part a ..., a chaque
  modification. »).

## 8. Divers

- Steerco : le compteur parle de plateformes, et les indicateurs rattaches a aucune
  squad sont signales avec un lien pour les attribuer.
- Preferences : les notifications du fil n'apparaissent que si le fil est actif ;
  l'avertissement SMTP n'apparait qu'une fois.
- Vocabulaire : « Fil » (plus « Tweet zone »), « Porteur » (plus « Owner »),
  « Squad leader » partout, « Abonnement au rapport » pour l'e-mail personnel. Les
  tirets servant de separateur ont disparu des libelles.
- Dates au format du reste de l'application, legende du tableau de bord corrigee,
  icone propre a la roadmap, erreurs affichees au lieu d'etre avalees.

## Ou est le code

- `backend/app/deps.py` : `leads_squad`, `reports_for_squad`, `can_report`.
- `backend/app/routers/squads.py` : `_set_contributors`, portee de lecture.
- `backend/app/routers/snapshots.py` : `pending`, `_keyed`, `_diff`.
- `frontend/src/pages/MySquadsPage.tsx` : `EditSquadModal` (deux modes).
- `frontend/src/pages/admin/organisation.tsx` : `SquadsAdmin`, `PeopleCell`.
- `frontend/src/pages/admin/configuration.tsx` : `ReportingAdmin`, `RecipientList`.
