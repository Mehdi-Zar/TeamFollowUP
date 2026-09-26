# Changelog

## Unreleased

### Passes de qualite (10 passes experience et technique, 3 passes mails et PPTX)
- **Mails lisibles partout** : un resume en tableaux (Outlook, Gmail, telephone), un bouton
  vers l'application, une ligne « pourquoi vous recevez ce mail » ; le PPTX joint, le HTML
  complet seulement sans lien vers l'application. Voir
  [32 - Mails et documents envoyes](docs/32-mails-et-documents-envoyes.md).
- **Avis de modification** : declenches par la soumission du reporting (par defaut),
  regroupes, jamais envoyes a leur auteur, avec ce qui a change ; remis en file si le
  serveur de mails refuse.
- **Rapport programme** : heure de Paris, une adresse recoit un document une seule fois,
  rien n'est perdu quand le serveur de mails est en panne.
- **Acces** : la personne validee ou refusee est prevenue par mail.
- **PPTX** : synthese paginee et triee par gravite, derniere saisie, slides datees, versions
  passees signalees, aucun texte sous 8 pt, slide « Points d'attention », roadmap avec
  statuts, organigramme lisible, Steerco filtre par plateforme.
- **Saisie et tableau de bord coherents** : une squad perimee demande une confirmation dans
  la saisie ; « Soumis il y a N jours » ; bandeau « Ouvrir mon reporting » ; qui a soumis
  dans l'historique ; retour a la page demandee apres une connexion SSO.
- **Erreurs** : messages lisibles (reseau coupe, delai, redemarrage, validation nommant le
  champ, reference d'erreur) ; session expiree sans perdre la saisie ; ecran de secours au
  lieu d'une page blanche.
- **Accessibilite et petits ecrans** : focus visible, fenetres annoncees, contrastes, tableaux
  et panneaux qui tiennent sur un telephone.
- **Schema** : migration 0038 (index et contraintes manquants en production) et
  `scripts/check_schema_drift.py`.

### Added
- **Le contributeur.** Un persona qui fait le reporting d'une squad sans la diriger :
  nomme par squad (par le tribe leader ou par le leader), il remplit et soumet la
  saisie, et ne touche pas a la fiche, a l'equipe ni au budget.
- **Mes squads pour le squad leader** : ses squads et elles seules, gerees en entier
  (fiche, OTD, equipe, budget, comites, contributeurs). Co-leaders et contributeurs
  visibles sur les cartes et dans le tableau Administration > Squads, ou ils
  s'ajoutent aussi.
- **E-mail a chaque modification, refait** : ses propres destinataires, le tribe leader
  et les squad leaders ajoutes par un bouton, et la regle resumee en une phrase.
- **Reglages generaux : le choix de la langue s'active ou non.** Coupe, le selecteur FR/EN
  disparait et toute l'instance s'affiche dans la langue par defaut, qui reste reglable au
  meme endroit. Les reglages s'appliquent des l'enregistrement, sans recharger la page.
- **Plateformes et Steerco : un seul menu.** Le tribe leader y impose le modele de Steerco
  de sa tribu (KPI, sous-indicateurs, SLA), declare ses plateformes (une plateforme, un
  Steerco), choisit les squads concernees, ajuste le squelette plateforme par plateforme
  et importe l'Excel. La saisie reste dans Reporting ; l'onglet Steerco du tableau de bord
  s'ouvre a toute la tribu. Les chiffres suivent desormais leur libelle quand le squelette
  change. Voir [15 - Steerco](docs/15-steerco.md).
- **Personas et droits : un seul tableau, et tout se choisit.** Une ligne par section de
  l'application et par onglet d'administration, groupees comme les menus, une colonne par
  persona. Tous les onglets, y compris ceux reserves jusqu'ici a l'administrateur (SMTP,
  SSO, sauvegardes, journaux...), se cochent pour n'importe quel persona, et le serveur
  suit (`app/tabaccess.py`). Seule la colonne de l'administrateur reste verrouillee, et
  « Voir en tant que » reste le sien. Le menu Administration apparait des qu'un persona a
  un onglet.
- **La prise en main s'ouvre au demarrage, dans une fenetre**, avec les etapes du role en
  tuiles cliquables et une case « Ne plus afficher au demarrage ». Elle quitte le menu
  lateral et se rouvre a tout moment par le bouton ? de la barre du haut.
- **Rapport planifie a la carte, par tribu.** Le tribe leader regle le rapport de sa
  tribu dans l'administration, l'admin garde le planning global. Chaque planning choisit
  ce que recoivent ses destinataires : le document complet, un mail par squad (avec les
  squads choisies), et le document de sa squad pour chaque squad leader. Un bouton envoie
  tout de suite a chaque squad leader le document de sa seule squad, et la page d'une
  squad a son bouton « Envoyer au squad leader ». Voir
  [30 - Rapports, notifications et droits](docs/30-rapports-notifications-et-droits.md).
- **Le mail de modification dit qui a modifie quoi**, en tete du message, et part
  aussi sur les engagements de squad, les KPI, les comites, l'equipe et le moral. Le
  tribe leader et les squad leaders peuvent le recevoir d'une case.
- **Personas et droits : les onglets d'administration du tribe leader se choisissent**,
  et un onglet decoche est aussi ferme cote serveur.
- **Deux engagements OTD au plus par mois** (par tribu pour le management, par squad
  pour une squad).
- **Un membre d'equipe est relie a son compte, par son email.** Rien ne posait ce lien :
  un membre ajoute depuis un ecran n'etait qu'un nom, et ses conges ne remontaient pas a
  son squad leader. On l'ajoute maintenant par son email, avec prenom et nom facultatifs ;
  les comptes de la tribu sont proposes pendant la saisie. Un compte existant est relie tout
  de suite, sinon a sa premiere connexion (ou a sa creation, ou a la validation de son
  acces). Jamais d'une tribu a l'autre. Migration `0036_member_email`.
- **Une version d'un document : le dashboard, la roadmap ou le rapport tels qu'ils etaient a
  une date passee.** Une squad fige sa saisie a chaque soumission de cycle, et cette photo ne
  se lisait que d'un seul endroit, l'historique de la page d'une squad, une soumission a la
  fois. La question posee apres coup n'est pas celle-la : c'est « montre-moi le dashboard tel
  qu'il etait le 12 septembre », et le seul recours etait de restaurer une sauvegarde de la
  base entiere, c'est a dire de faire reculer l'application pour tout le monde. Le menu
  Exporter propose desormais une **version**, qui est une journee et non une soumission : les
  jours ou une squad du perimetre a soumis, avec le nombre de squads concernees, parce que
  c'est ce chiffre qui dit si la version est complete. Le choix vaut pour les trois formats et
  pour l'envoi par courriel (`as_of` sur `weekly`, `dashboard`, `roadmap` ; `GET
  /api/reports/versions` pour la liste). Le document rejoue ne recalcule rien : il reprend
  pour chaque squad sa derniere saisie anterieure a la date, et **recompte ses jalons bloques
  sur les jalons figes** - un jalon debloque depuis aurait fait etat de zero bloqueur dans une
  version qui en comptait trois. Une squad qui n'avait rien soumis sort du document et son nom
  est compte, plutot que d'etre remplacee par son etat du jour : un document complet en
  apparence et faux en un point est le pire des deux. La mention `version du ...` voyage a
  cote de l'heure de generation. Le budget, lui, reste celui du jour et n'entre pas dans la
  saisie figee : celle-ci se lit par tout utilisateur qui voit la squad, ses chiffres de
  budget non. Voir [29 - Les versions d'un document](docs/29-versions-des-documents.md) et
  [ADR-0016](docs/adr/0016-a-version-is-a-day-replayed-from-frozen-submissions.md).

- **La saisie figee porte ce que les documents relisent.** Elle gardait les objectifs, les
  jalons, l'avancement et les KPI, ce qui suffit a comparer deux soumissions mais pas a
  rejouer un document : sans les engagements OTD, sans les rattachements `otd_id` /
  `squad_otd_id` des jalons, sans les messages cles, les initiatives, le moral ni l'avancement
  annuel, une version passee se serait reconstruite avec les liens et les dates d'aujourd'hui.
  Les saisies anterieures restent lisibles : ce qu'elles n'ont pas sort vide, jamais rempli
  avec la donnee du jour.

### Changed
- **Saisie et reporting : un seul endroit pour modifier chaque donnee.** La saisie
  montre ce qui a change depuis la derniere soumission, etape par etape, et seul le
  leader de la squad soumet ; la page de squad lit (moral, messages, OTD, KPI visibles
  par toute la tribu) avec un lien vers la saisie ; une seule fenetre de rapports pour
  tout le monde. Voir [31 - Coherence de la saisie](docs/31-coherence-saisie-et-reporting.md).
- **Les courbes du graphe KPI Steerco ne se confondent plus.** Deux des six couleurs de
  series tenaient du meme bleu marine, a 5,5 d'ecart sur 100 : deux courbes de la meme
  plateforme etaient litteralement de la meme couleur, et la legende restait le seul moyen
  de les separer. Un gris-bleu pale et un ambre clair passaient par ailleurs sous les 3 pour
  1 de contraste sur fond blanc, donc s'effacaient au videoprojecteur. Les six nouvelles sont
  choisies par calcul : 25,9 entre voisines, 17,7 une fois simulee une protanopie ou une
  deuteranopie, 13,8 entre les deux plus proches quelles qu'elles soient, et toutes
  au-dessus du contraste minimal. Elles restent a distance du vert, de l'ambre et du rouge,
  qui sur cette page disent la sante d'un SLA et les incidents : une courbe ne doit pas avoir
  l'air de le dire aussi. Un test mesure ces ecarts au lieu d'en juger a la relecture.
- **Un squad leader voit ses engagements, et les prend dans son cycle de reporting.** Il
  pouvait deja le faire : l'API acceptait son engagement de squad et le lui renvoyait. Mais le
  seul ecran qui le proposait etait la page de sa squad, atteinte par un clic dans une liste,
  et « Mes squads » comme le Reporting n'en disaient rien. En pratique, personne ne trouvait
  le bouton. L'etape **Engagements** suit desormais celle des jalons, la ou on rattache ceux
  qu'on vient d'ecrire : ce que le management attend de la squad en lecture, les engagements
  de la squad en ecriture, et la liste de controle de l'envoi gagne une ligne non bloquante.
  Elle avait ete retiree du parcours quand personne ne pouvait l'y ecrire ; la portee squad a
  change cela, et c'est pour elle qu'elle revient. Voir
  [27 - Le parcours de reporting](docs/27-parcours-de-reporting-et-listes.md).
- **Un engagement management se lit par tous les squad leaders de sa tribu.** Il n'etait
  visible que de la personne a qui il etait assigne nommement, ou une fois un jalon rattache.
  Or seul le tribe leader rattache un jalon : l'engagement pose sur une squad restait donc
  invisible a celui qui devait le tenir tant qu'un autre n'avait pas agi, et rien ne le lui
  signalait. Un engagement qu'on ignore ne peut etre ni tenu ni conteste, et celui qui change
  de titulaire restait visible du seul ancien. La lecture s'arrete a la tribe, et l'ecriture
  n'a pas bouge d'un pouce : le squad leader lit, il n'ecrit que le sien.
- **Un co-leader dirige aussi, a l'ecran comme au serveur.** `deps.leads_this_squad` compte le
  leader nomme et ses co-leaders depuis toujours ; l'interface ne lisait que `leader_user_id`.
  Un co-leader avait donc tous les droits d'ecriture a l'API et aucun bouton pour les exercer,
  sur les jalons, les messages cles et l'engagement de sa squad. Une co-direction que l'ecran
  ignore n'est pas une co-direction.
- **Le graphe KPI du one-pager Steerco : une seconde echelle a droite pour les courbes hors
  d'echelle.** Une Software Factory qui compte ses builds par milliers ecrasait le reste de la
  plateforme : DBaaS a 12 instances et K8aaS a 30 se confondaient avec l'axe, sur un graphe
  dont le seul objet est de montrer leur evolution. Quatre courbes sur cinq etaient illisibles
  au profit de la seule qui n'avait pas besoin du graphe pour se voir. Les series sont
  desormais triees par valeur maximale et coupees au plus grand ecart d'ordre de grandeur :
  passe un facteur 5, le groupe du haut se lit sur une echelle propre, graduee a droite, et la
  legende dit quelle courbe se lit de quel cote : sur la page en deux groupes nommes (« axe
  gauche », « axe droit »), donc une fois par echelle et non une fois par courbe ; sur la
  diapositive derriere chaque nom de serie, la legende etant celle de PowerPoint, ou l'on ne
  range rien. Sous ce facteur, le graphe
  garde un seul axe, puisqu'un second ne serait qu'une colonne de nombres de plus a lire. La
  coupe se deduit des chiffres du mois, il n'y a rien a parametrer, et elle vaut pour les deux
  rendus : le HTML consulte dans l'application et la diapositive PPTX emportee au comite, ou
  l'axe secondaire est ecrit directement dans la partie graphique, python-pptx ne l'exposant
  pas. Voir [15 - Steerco](docs/15-steerco.md).
- **Les diapositives exportees se lisent de plus loin : le texte est agrandi d'un cran.**
  Les corps etaient cales sur une lecture a l'ecran, a 40 cm; un deck se lit projete au fond
  d'une salle, et le rapport comme le one-pager Steerco y passaient trop petits. Un facteur
  unique les agrandit (`pptxtpl.FONT_SCALE`), applique au seul endroit ou un nombre devient
  une taille de police, et ce qui se deduit d'un corps (hauteur de ligne, caracteres par
  ligne, largeur d'une pastille) passe par le meme facteur : sinon le texte grossirait dans
  des boites restees a l'ancienne mesure. La ou une mise en page choisit son corps en
  descendant une echelle jusqu'a ce que tout tienne, elle part de plus haut et retombe
  d'elle-meme sur l'ancien corps quand la place manque, donc **agrandir ne fait disparaitre
  aucune boite**. Trois endroits restent hors du facteur parce que leur taille est dictee par
  la place et non par le confort : le nom d'une squad couche dans sa bande, le texte d'une
  carte d'organigramme, et la legende du bas de slide, qui prend le corps commun tant que sa
  rangee tient dans la largeur et redescend sinon. Voir
  [24 - Les exports d'une squad](docs/24-exports-frise-annuelle-et-moral.md).
- **Le titre d'un trimestre ne s'ecrit plus sur sa barre d'avancement.** La barre etait
  posee a une distance fixe du haut de sa carte, calee sur un corps de 13 points. Le texte
  ayant grandi, sa ligne descendait plus bas que cette distance et « Q4  50 % » se retrouvait
  ecrit par-dessus. La hauteur de la carte et la position de la barre se deduisent desormais
  du corps reel, et un test mesure la ligne au lieu de faire confiance au chiffre.
- **Les cartes de l'organigramme ne se chevauchent plus, et les noms tiennent dedans.** La
  largeur d'une carte avait un plancher d'1,1 pouce ; a quatorze squads, un emplacement n'en
  fait plus que 0,9, et chaque carte mordait sur sa voisine. Elle ne depasse plus son
  emplacement. Et comme PowerPoint passe un titre a la ligne mais ne coupe pas un mot,
  « Management » sortait de sa carte des deux cotes : le corps descend maintenant jusqu'a ce
  que le mot le plus long rentre, et le mot est coupe en dernier ressort.
- **Le bloc Budget d'une slide de squad tient enfin dans son cadre.** « Prevision » sortait
  par le bas et se lisait a moitie : la carte etait plus courte que son titre et ses trois
  lignes, ce qu'aucun test ne disait. Elle a desormais la hauteur qu'il lui faut, prise sur
  la frise qui en avait de reste, et un test mesure le texte contre le cadre plutot que de
  faire confiance a des coordonnees.
- **L'axe de la frise est decoupe par trimestre, dans les deux bandes a la fois.** La carte
  d'un trimestre prenait toute sa gouttiere a droite : elle etait plus courte que ses trois
  mois et Q1 s'arretait avant la fin de mars. Et la bande des mois etait d'un seul tenant
  sous des cartes separees, donc rien n'y disait ou un trimestre finissait : mars semblait
  deborder de Q1. Un trimestre et ses trois mois forment desormais **un bloc**, janvier,
  fevrier et mars ensemble sous Q1, et la meme gouttiere separe deux blocs en haut comme en
  bas. Tout ce qui se pose sur un mois (l'etoile d'un engagement, le trait d'une boite, la
  largeur d'une case) suit la meme grille, donc rien ne se decale. Un test mesure la coupure
  dans les deux bandes plutot que de faire confiance aux coordonnees.
- **Le bouton « Exporter la roadmap » quitte la page Reporting.** Il doublait le menu
  Exporter de la barre de page, sur la seule page qui sert a saisir et non a lire, et il
  n'offrait qu'un format et qu'une portee la ou le menu les offre tous. Les documents se
  prennent a un seul endroit.
- **La frise des exports : les engagements dans leur case de mois, les jalons dans des boites
  reliees a leur date.** Trois regles tiennent desormais la mise en page, et chacune repond a
  une facon dont les versions precedentes se sont defaites.

  **Un engagement tient dans la largeur d'une case de mois**, son titre passant a la ligne.
  Ecrit a cote de son etoile, il courait sur trois ou quatre mois: on ne savait plus a quelle
  colonne il repondait, et il fallait trois bandes superposees la ou une suffit. Deux
  engagements du meme mois se suivent dans la meme colonne, l'un sous l'autre.

  **Une boite de jalons ne sort jamais du trimestre de sa date**: elle peut commencer un mois
  plus tot pour y tenir, mais pas deborder sur le suivant, ou elle se lisait sous le mauvais.
  Les boites d'un meme trimestre **s'empilent sur une seule colonne**, larges de tout le
  trimestre; on n'en ouvre une deuxieme que lorsque la pile ne tient plus dans la hauteur, ce
  qui est rare, la frise ayant de la hauteur et peu de largeur. Seule la tete de chaque pile
  recoit son trait, les suivantes portant leur mois devant leur titre. Le corps du texte suit
  la charge, de onze points et demi a six et demi, plutot que de renoncer a une boite: un jalon
  ecrit petit se lit encore, un jalon absent ne dit plus rien. Une boite porte un titre (l'engagement que ses jalons tiennent, ou leur theme a
  defaut) et une seule date, ce qui est la condition pour qu'un trait suffise a dire quand ses
  jalons sont attendus.

  **Le trait remonte droit jusqu'au mois, en pointille et d'une encre claire**: il relie, il ne
  cloisonne pas. Pour passer, il longe le bord de la case du mois, qui est inseree de chaque
  cote pour lui laisser un couloir libre sur toute la hauteur de la bande. Les versions
  precedentes faisaient passer ces traits au milieu des titres, puis derriere eux, puis dans les
  couloirs libres entre eux, puis en coudes dans une gouttiere.

  **Chaque jalon porte une coche, a droite de son titre**, et elle dit ses trois etats par le
  dessin autant que par la couleur: pastille pleine et cochee quand il est livre, anneau avec
  un point au centre quand il avance (en cours, a risque, bloque), anneau vide quand il n'a pas
  commence. Deux anneaux identiques ne distinguaient pas ce qui avance de ce qui dort, et une
  couleur seule ne se lit pas une fois la slide projetee. Elle mesure un millimetre et demi de
  plus qu'avant: a deux millimetres elle passait pour absente. A gauche, elle decalait chaque
  titre de sa largeur, et un oeil qui descend une liste lit des titres alignes. Sa legende,
  au bas de la slide, passe en 9 pt et **ne revient plus a la ligne**: en 7 pt sur une largeur
  estimee trop courte, le libelle se coupait et sa seconde ligne tombait hors de la slide, ce
  qui donnait une frise sans legende sur les modeles dont la police est large.

  **Le moral tient en trois mots et un nuage**: « Team » au-dessus, « Mood » en dessous, le
  nuage a droite. Ce nuage est desormais **le meme dessin sur les deux supports**: son contour,
  ses yeux et ses trois bouches sont decrits une seule fois, l'ecran et le HTML les rendent en
  arcs SVG, la slide en polygones echantillonnes sur ces memes arcs. Le deck prenait jusqu'ici
  la forme « nuage » de PowerPoint, qui a ses propres bosses: le document montrait donc une
  autre icone que l'application, ce qu'un logo ne peut pas se permettre. Le niveau n'est plus ecrit a cote, il se lit sur le visage et sur la couleur,
  et l'ecrire revenait a le dire deux fois dans deux centimetres. Le nuage est desormais plein
  et non pastel: pose en haut d'une slide a cote d'un bandeau navy, une teinte claire cernee
  d'un filet fin disparaissait.

  Sept invariants sont tenus par des tests sur le jeu de donnees dense, sur les treize slides:
  aucun texte n'en recouvre un autre, aucun titre n'est coupe, aucune forme ne sort de la
  slide, aucun engagement ne deborde de sa case, aucun trait ne touche un engagement, deux
  engagements du meme mois sont empiles, et chaque jalon a sa coche. Le HTML suit le meme
  dessin; sa page s'elargit avec le nombre de boites, pour que le JPG les montre toutes.

### Removed
- **Objectifs de squad.** L'OTD est le seul engagement : la route `/api/objectives` et
  l'interrupteur `squad_content.objectives` disparaissent, la tuile « objectifs rouges »
  devient « OTD en retard ». Les pages `/print/*` sont aussi retirees.
- **In-app TLS termination, and with it the private key that lived in the database.** The
  app shipped two serving modes: plain HTTP on :8000 with the Gateway/ALB doing TLS, which
  is what every real deployment ran, and HTTPS on :8443 with a certificate an administrator
  generated or imported from Admin. The second one was the default in code and the path
  nobody used, and it cost: the unencrypted server key sat in the `tls` settings row, so it
  followed every `pg_dump` into the backups; the toggle could not apply itself, since the
  listener is bound at boot, which is where the "pending restart" banner and the
  `restart_pending` field came from; flipping it on a Gateway-fronted deployment moved the
  pod to 8443 in front of a Gateway still expecting 8000; and the cookie policy had to track
  a mode changeable from a web page. A load balancer does TLS better and one is already
  there. So the app now serves plain HTTP only, `proxy_headers` giving it the original
  scheme and host, and HTTP→HTTPS redirection stays where it always belonged.
  `TLS_ENABLED`, `HTTPS_PORT`, `APP_HTTPS_PORT`, the Admin toggle, self-signed generation,
  PEM/PFX import and the served-chain assembly are gone, along with `tls.py` and
  `tlsconfig.py`, replaced by `certinfo.py` (reading certificates) and `trustconfig.py` (the
  store). Migration `0028_trust_store` rewrites the settings row keeping only the
  authorities: **the certificate and its key are dropped, which is the point.** Export a
  certificate you only kept in the app before upgrading. See
  [ADR-0013](docs/adr/0013-tls-terminated-by-the-infrastructure.md).

- **142 dead translation keys, and a test so they do not come back.** 1165 keys, 1023 of them
  actually reachable: the rest were leftovers from an OTD screen, an older dashboard, a
  reporting and subscription UI and an export menu that had each been redesigned. Dead labels
  are not free. They get read as an inventory of what the product does, they get translated,
  and they bury the live ones. Removing them safely needed the reachability question answered
  properly, not guessed: a key counts as used when it is named anywhere in the source, or when
  a template literal can build it (`` t(`leaves.status.${s}`) ``). Both were resolved from the
  code, every candidate was cross-checked against every dynamic prefix, and the families that
  looked alive but were not (`brand`, `dash.filter.all` next to a live `dash.filter.all_f`)
  were confirmed one at a time. `i18n.usage.test.ts` now holds both directions: no key the code
  asks for may be missing, since `t()` falls back to printing the raw key on screen, and no key
  in the dictionary may be unreachable. It discovers the dynamic prefixes from the source
  rather than from a list, so a new family is protected without anyone remembering, and both
  halves were checked against a planted violation.

### Changed
- **Admin → HTTPS / Certificats becomes Admin → Autorités de certification**, and manages one
  thing: the authorities the app verifies its own outbound calls against (OIDC, SAML, SMTP,
  log export). That was always the half of the screen that had nothing to do with who
  terminates the inbound TLS, and importing an internal root is still what makes a privately
  issued IdP reachable without ever disabling verification. The API moves from
  `/api/admin/tls-config` to `/api/admin/trust-store`, the audit actions from `tls_config.*`
  to `trust_store.*`.

### Fixed
- **Cinq passes d'audit de la saisie et du reporting**, chacune corrigée et testée (voir
  [31](docs/31-coherence-saisie-et-reporting.md)) : le contributeur voit sa squad en écriture,
  rattache ses jalons et a ses liens ; un leader d'une squad d'une autre tribe la lit, la saisit
  et l'exporte, sans en régler la structure ; une clé d'API liée à une tribe ne voit plus les
  squads sans leader des autres tribes ; supprimer une squad ne supprime plus l'OTD du
  management posé sur elle ; les exports suivent l'année et la langue de l'écran et nomment
  co-leaders et contributeurs ; les envois automatiques suivent l'année de référence ; erreurs
  affichées au lieu d'être avalées ; « tribe », « Porteur », « Fil » partout ; textes d'aide,
  guide des menus et documentation remis à jour.
- **Ce qui se lit ou s'ecrit par identifiant reste dans la tribu de l'appelant.** Les
  listes filtraient par tribu, les routes d'un seul element non. Un compte non-admin sans
  tribu (cree sans, ou laisse par la suppression de sa tribu) etait traite comme un admin
  et voyait toutes les tribus : il ne voit plus rien. Les saisies figees d'une squad d'une
  autre tribu ne se lisent plus, un message du fil d'une autre tribu ne se supprime,
  n'epingle, ne commente ni ne se like plus, et un tribe leader ne modere que les messages
  de sa tribu (un message global reste a l'admin). Le fil envoie `can_delete` et `can_pin`
  par message, pour que l'ecran ne propose plus un bouton refuse. Un tribe leader ne
  retablit plus un compte revoque d'une autre tribu, ni un ancien administrateur.
- **Un `null` ou un nom vide envoye en modification renvoie 422, plus un 500.** Un seul
  garde-fou (`deps.update_data`) sert tous les PUT : `null` sur une colonne obligatoire,
  nom ou titre vide. Les schemas de creation refusent aussi un nom vide.
- **Les references sont verifiees avant la cle etrangere.** Initiative d'un objectif
  (existante et de la meme tribu), squad ou tribu d'une dependance de jalon, squad d'une
  boite de l'organigramme (de la meme tribu), tribu d'un compte ou d'une cle d'API,
  proprietaire d'un OTD de squad (un de ses leaders, a la creation comme a la
  modification). L'organigramme refuse aussi de placer une boite sous l'une de ses
  descendantes : la branche disparaissait.
- **Supprimer une squad ou une tribu n'echoue plus sur une cle etrangere.** Les jalons des
  autres squads gardent leur dependance, en texte libre au nom de la cible. Les abonnements
  a la squad partent avec elle. Une tribu se supprime une fois ses squads, initiatives et OTD
  partis ; ses messages du fil et ses cles d'API sont supprimes (sans tribu, ils seraient
  devenus globaux).
- **La remise a zero et la restauration des donnees sont atomiques.** Lancees par un admin
  autre que le compte de secours, elles finissaient en 500 apres avoir deja efface : un
  commit au milieu, puis une ligne d'audit vers le compte qu'elles venaient de supprimer.
- **Export PPTX du dashboard : la legende remonte**, avec une marge sous elle. L'entete
  et la frise remontent pour lui faire place, sans rien retirer a la hauteur des jalons.
- **Le squad leader arrive directement sur sa squad dans la saisie**, sans selecteur
  quand il n'en dirige qu'une.
- **L'avancement annuel ne compte que les trimestres qui ont des jalons.** Un trimestre sans
  rien de prevu comptait pour 0 : une squad dont tout le travail, termine, tenait en T1 et T2
  plafonnait a 50 % et ses objectifs passaient au rouge a l'automne.
- **Le reporting ne montre plus « les autres engagements de la tribu »**, qui repetait sous
  chaque squad des engagements qui ne la concernent pas.
- **Conges** : la case « precision obligatoire » d'un type est enfin enregistree, une
  absence deja decidee ne se decide plus (409), et l'alerte de chevauchement compte des
  personnes, pas des absences.
- **Divers** : la periode Steerco doit etre un mois `AAAA-MM` (422 sinon, au lieu d'un 500) ;
  enregistrer la config du rapport ne relance plus un envoi deja fait le jour meme ; les
  abonnements ne partent plus vers un compte revoque ; un admin arrete une simulation meme
  sur un compte en attente.
- **Ecrans** : les erreurs d'enregistrement s'affichent la ou l'on travaille (fenetres de
  jalon, de comite, d'OTD, de squad, d'equipe ; KPI, messages cles, moral, fil) au lieu
  d'etre avalees ou cachees derriere la fenetre. L'organigramme n'efface plus le nom de la
  personne d'une boite modifiee et une erreur n'y remplace plus toute la page. La saisie ne
  propose plus au tribe leader les jalons et messages cles que le serveur lui refuse. Un OTD
  sans proprietaire ne se rattache plus a une squad sans leader. Les membres peuvent publier
  dans le fil quand l'admin l'a ouvert a tous. Les jours d'abonnement ne s'affichent plus en
  cle brute, et l'envoi par courriel suit l'annee et la version choisies.
- **Deleting a user returned 500 for anyone who had ever logged in.** Nineteen columns
  reference `users.id`, every one with `NO ACTION`, and `DELETE /api/admin/users/{id}` detached
  none of them: the first audit row the person produced, which logging in writes, was enough to
  block the delete. So the right to erasure was not exercisable from the application, and
  docs/20 pointed at the very screen that failed. The policy was never in doubt, it was written
  in three places (the `AuditLog` model docstring, docs/20 section 5, and `prune_users.py`) and
  the endpoint was the only thing not applying it. New `app/userpurge.py` applies it: the
  person's own records go with them, deleted through the ORM so the declared cascades run, and
  every other reference is detached so somebody else's work and the audit trail survive. The
  detach set is derived from the schema, so a table added later needs no one to remember; a new
  **non-nullable** reference raises instead, because "is this personal data" is a decision.
  `prune_users.py` now uses the same code, where it previously covered two of the nineteen
  columns and would have failed on a user with a notification. Verified against PostgreSQL on
  accounts that really were blocked: the audit trail went from 562 rows to 563 (the deletion
  entry) with the person's rows anonymised rather than destroyed.
- **The test database did not enforce foreign keys, which is why nothing caught the above.**
  SQLite ignores them unless asked; production runs PostgreSQL, which does not. A
  `PRAGMA foreign_keys=ON` listener is now installed on the test engine. It broke no existing
  test, so the gap was purely in what the suite was able to see.
- **The end-to-end suite left a user behind on every run.** Its cleanup deleted the member it
  created but never asserted the result, so it had been silently receiving that same 500 since
  the suite was written. Unasserted cleanup is cleanup that does not happen: the delete is now
  asserted to return 204.

### Added
- **Four end-to-end tests for the two changes that only unit tests were holding.** The suite now
  runs 34. `admin-https.spec.ts` opens the HTTPS section on the compose stack, where the
  infrastructure terminates TLS, and asserts what the regression got wrong: the
  served-certificate panel is hidden and says why, while the trusted authorities are present
  with enabled controls. `language.spec.ts` asserts that a profile which has never chosen a
  language gets the instance default and stores nothing, then that a choice survives a reload.
  It is the one spec importing `test` from `@playwright/test` rather than from `./helpers`,
  because the shared fixture pins the language and here its absence is the case under test.

### Changed
- **The typography rule now covers the whole repository, with no allowlist.** It was scoped to
  "anything a user reads", and that boundary was the problem: it needed adjudicating on every
  edit and nobody did it, which is how the weekly report ended up shipping the middot as its
  separator. 185 em dashes and 153 middots are gone. The em dashes were mostly route
  docstrings, `GET /api/x` followed by a dash and a summary, now a colon; those are not
  internal prose, FastAPI publishes them as endpoint descriptions into Swagger UI and into the
  committed OpenAPI snapshot. The middots were list separators: 92 in the API reference (now
  semicolons, which a comma could not do without colliding with the commas already inside the
  items), plus ADR headers, deployment titles, the definition-of-done checklist and the
  CHANGELOG's own prose. `CLAUDE.md` names the two characters by code point and the guards
  write them as escapes, so the rule file and its tests pass their own rule and nothing needs
  exempting. `backend/tests/test_typography.py` is now a flat repository-wide scan, checked
  against a planted violation, with a second test asserting it really looks at something (an
  over-tight filter would leave it permanently green).

### Fixed
- **`leaves > overlap_alert` was the last feature flag with no effect on screen.** The
  calendar called `GET /api/leaves/overlaps` unconditionally and swallowed the refusal in a
  `.catch`. The behaviour was right, the banner never appeared, but it meant a request the app
  already knew would be refused on every month change, in the network panel and the access
  logs. The page now asks the module map first. And a new test asserts that **every** declared
  feature flag is enforced server-side, in one of the two legitimate shapes: `require_module`
  on the route when the feature owns endpoints, or `is_active` where it acts when it governs a
  field or a side effect. That is the guard that would have caught `feed > kinds`.
- **The instance's default language never reached the interface.** `default_lang` (Administration
  > Settings, French out of the box) drove the weekly report and the notification emails
  correctly, but never the SPA: `I18nProvider` wrote `trt_lang` from a mount effect, stamping
  `en` into localStorage before `/api/config` had answered, and `ConfigProvider` then read that
  stored value as "the viewer has chosen a language" and declined to override it. So a French
  instance greeted every new visitor in English while emailing them in French, and the setting
  did nothing. `trt_lang` is now written only when someone actually picks a language, which is
  what its presence was always meant to mean, and the "chosen or not" test lives in `i18n.tsx`
  beside the key it depends on (`storedLang`, `applyServerDefault`). The default is applied
  without being persisted, so changing it in Administration reaches everyone who has not chosen,
  not only first-time visitors. Four tests pin the four cases.
  The Playwright suite was relying on this bug: it names English labels and got English for
  free. It now pins the language itself, in the `test` fixture exported by `tests/helpers.ts`,
  before the first navigation, so it no longer depends on a setting an administrator may change.

### Added
- **The rendered documents are now tested, not just the code that builds them.** Coverage
  exposed something worse than the typography defect it was there to check: most separator
  sites in the weekly report were never executed by the suite, and the single-squad deck
  builder (`squad_page_slide`, 130 lines) was reached by nothing at all. The shared fixtures
  carry no budget, no deadlines, no dependencies and no key messages, and the budget is
  withheld unless a viewer is passed, so the richest half of the flagship deliverable shipped
  unexercised. `test_report_typography.py` fills a squad with all of it, renders all eight
  documents for a real viewer, and reads the output: the banned characters must be absent, and
  the replacements must still carry their information. `reportpptx.py` goes from 64.7% to
  95.9% covered, `report.py` from 81.5% to 87.1%, the suite from 77.3% to 80.1%, and the
  coverage ratchet moves 76 to 79.

### Fixed
- **The security documentation claimed a guard that does not exist.** docs/05 stated that all
  seven persona capabilities are enforced server-side by `require_capability`. Six are
  (`dashboard`, `roadmap`, `org`, `feed`, `reporting`, `leaves`); `mysquads` is navigation only.
  That is the right design, not a hole: the screen it opens drives `PUT /api/squads/{id}`,
  which also carries the budget toggle on the squad page and the Steerco toggle on the entry
  page, so gating that route on the capability would break unrelated features for a persona
  that merely has a menu entry hidden. The actions are guarded by role and ownership instead
  (`require_tribe_or_admin` on create and delete, tribe scope plus reserved structural fields
  on update). The claim is now precise in docs/05 and docs/01, and a test asserts which
  capabilities carry a guard, so the documentation cannot drift from the code again.
- `BACKUP_RETRY_SECONDS` was read by the backup sidecar but missing from `.env.example`, where
  its two siblings were documented.
- **One feed feature flag was a suggestion, and one setting did nothing at all.** Both found
  while auditing for the same defect class as the trusted-authority store: something that
  exists in the model and the API surface without being wired to an effect.
  `feed > kinds` hid the kind selector in the SPA but gated no route, unlike its three
  siblings (`reactions`, `replies`, `pin`), which each carry `require_module`. A client could
  still post an `incident` and still filter on it with the switch off, so an admin decision
  about the data was enforced only by the screen. The API now coerces the kind to `info` when
  the feature is off and ignores the `kind` filter, with two tests pinning both directions.
  `feed_kinds` in the general settings was worse: stored, validated, published on the
  unauthenticated `/api/config` and typed in the SPA, but read by nothing. The kinds are
  structural (a Pydantic `Literal`, a TS union, a translation key and a colour each), so it
  could not be made configurable by wiring alone and was removed rather than left as a promise.
- **CI carried two implementations of the i18n parity rule.** A 14-line inline node script
  duplicated `i18n.parity.test.ts`, which `npm test` already runs in the same job. The script
  is gone; the test is the single implementation, and it runs locally too.
- **The report and the PPTX shipped the one character the project bans.** `CLAUDE.md` forbids
  the em dash and the middot in anything a user reads, generated HTML and PPTX documents
  included, because they read as machine-written. The weekly report used the middot as its
  separator throughout: the squad headings, where it stood between the name and the progress
  percentage, the document header, budget lines, deadlines, dependencies, and the squad/tribe
  column of the dependency table. So did the
  PPTX export, the API-key label shown in the audit log, and the subject of every
  change-notification email. Each separator was replaced by what actually fits its sentence:
  parentheses for a supplementary figure (`Squad A (72%)`, `(Tribe)`), a comma inside a list of
  equal-weight items, a hyphen in deck titles where the other titles already used one, and
  `by`/`par <author>` in the email subject, where a name has to read as a name. Two guards keep
  it from coming back and run with the normal suites: `backend/tests/test_typography.py`
  inspects every non-docstring string literal under `backend/app`, so developer prose stays
  free, and `frontend/src/typography.test.ts` scans the frontend outside comment lines.
- **The trusted-authority store was locked behind an unrelated toggle, and did nothing for
  outbound calls anyway.** Connecting to an internal IdP over OIDC failed with
  `self signed certificate in certificate chain`, and the admin screen offered no way out:
  the whole CA section was rendered only when *the application terminates TLS itself*, so on
  the recommended deployment (infrastructure terminates TLS, `TLS_ENABLED=false`) an
  administrator was told to enable in-app TLS, which rebinds the listener from 8000 to 8443
  at the next restart, in front of a Gateway that expects 8000. Two unrelated concerns had
  been merged into one switch. Even after flipping it, the import would not have helped:
  imported authorities only ever fed the chain *served* to browsers, never the verification
  of the calls the app *makes*. The store is now managed in both serving modes, and it is
  merged with the public roots into an outbound trust bundle (`app/trust.py`) that every
  outbound call verifies against: OIDC discovery/JWKS/token exchange, SAML metadata, SMTP, the
  log export, and the SSO connectivity test, so a green test now means the login will really
  connect. `SSL_CERT_FILE` points at the same bundle as a net for anything whose client we do
  not construct. The public roots are always kept, and a bundle already supplied at deploy time
  is used as the base rather than replaced. Adding or removing an authority applies on the next
  outbound call, with no restart.
- **SAML metadata and SMTP were not verifying certificates at all.** The two workarounds that
  the missing trust store had made necessary: `parse_remote(..., validate_cert=False)` for the
  IdP metadata, and `starttls()` with no context, which makes smtplib fall back to
  `ssl._create_stdlib_context()` (`check_hostname=False`, `verify_mode=CERT_NONE`) and hand
  the SMTP credentials to whatever answered. Both now verify against the same store.
  **Behaviour change:** an internal SMTP relay or metadata URL with a privately issued
  certificate stops working until its authority is imported. That is the point, it was never
  verified before. There is deliberately no switch to turn verification off.
- **The deployment guide handed you a mutable image tag, and that breaks Alembic.** The GKE
  manifests pinned `teamfollowup:1.0`, a tag anyone naturally re-pushes on the next build.
  Kubernetes defaults `imagePullPolicy` to `IfNotPresent` for every tag but `:latest`, so a
  node that already cached it keeps serving the old image - and the symptom is not "the old
  version is running", it is the pod dying on
  `Can't locate revision identified by '0027_steerco_entries'`, because the database has been
  migrated past what that stale image contains. The manifests now use the version as an
  immutable tag, the build step says never to re-push one, and §11 gains the failure with the
  three commands that settle it (what the database believes, what the image carries, and which
  image is really running **by digest**, since the tag lies). It also says plainly not to
  reach for `alembic stamp`: stamping backwards leaves the tables that migration created in
  place but unrecorded, so the next deployment tries to create them again. The same warning is
  in the maintenance guide, where upgrades actually happen.

## 2.1 - Observability, end-to-end tests, and the promises that were not kept (2026-08-27)

> **One behaviour change to know about before upgrading.** "Message retention" now
> really deletes feed posts past its window, where it used to only hide them. An
> instance with a non-zero value starts deleting on the next scheduler tick. That is
> what the setting always claimed to do; pinned posts are exempt. See *Fixed*.

### Added
- **Observability: the app finally measures itself.** The only operational signals were the
  logs and the audit trail, which say what happened but never whether it is happening more
  than usual. New `/metrics` endpoint in the Prometheus format (`app/metrics.py`), fed by a
  pure-ASGI middleware placed outside everything else, so the latency it records is the one
  the client experienced. Exposed: traffic, error rate and latency **per route template**,
  in-flight requests, connection-pool saturation, weekly-scheduler health, login outcomes
  (success, failure, throttled) and the deployed version.
  The route label carries the template (`/api/squads/{squad_id}`) and never the real path;
  two tests lock that property down, because a mislabelled counter is the easiest way to
  take the monitoring down, weeks later and with no visible link to the offending commit.
  A scrape queries no database. The endpoint can be protected with `METRICS_TOKEN` (bearer)
  and switched off with `METRICS_ENABLED=false`; the app warns at boot when it is left open
  while `PUBLIC_BASE_URL` is set, that is, when this is clearly not somebody's laptop.
  New dependency: `prometheus-client`.
- **A ready-to-run observability stack** in [`ops/`](ops): the scrape config, **seven alert
  rules** each commented one by one (down, error rate, latency excluding exports, exports too
  slow, pool exhausted, scheduler wedged, login-failure spike), a pre-declared Grafana
  datasource, and a `docker-compose.observability.yml` kept separate from the product's own.
  One command and you have graphs.
- **[17 - Observabilité](docs/17-observabilite.md)**: what each metric measures, the
  cardinality rule and why it is not negotiable, the six PromQL queries worth knowing taken
  apart piece by piece, how to build the dashboard, what each alert means and what to do when
  it fires, how to protect `/metrics`, and the transposition to Kubernetes (`ServiceMonitor`)
  and to GKE (`PodMonitoring`).

### Added
- **[20 - Données personnelles et rétention](docs/20-donnees-personnelles-et-retention.md).**
  The application describes an organisation: people, their roles, and their **absences**. That
  is personal-data processing whether or not anyone called it that. The document lists what is
  stored and why, how long each kind is kept, who can see it, and the exact queries to answer
  an access request or an erasure request - including the decisions erasure actually requires:
  leaves and feed posts are deleted, but audit entries are **detached** (`user_id = NULL`)
  rather than destroyed, because the trail answers a separate legitimate interest and the
  schema was built nullable for exactly that. It also names the two things that deserve
  attention rather than burying them: `org_members` can describe someone who never opened the
  application, and the free-text leave reason is a field where somebody can write a medical
  reason.
- **[19 - Plan de reprise](docs/19-plan-de-reprise.md): the restore procedure, as executed.**
  The roadmap has wanted a DR runbook since the first audit. This one states the RPO and RTO
  the shipped configuration actually gives (24 h and about 15 minutes) and what to change to
  move them, and its procedure was **run** rather than imagined: a witness record created,
  backed up, deleted from the live database, and found again in a database restored from that
  backup. It also gives the drill that verifies a backup **without touching production** - the
  restore goes into a throwaway database beside the real one - and states the residual
  weaknesses plainly: the backups live on the same host as the database, they are not
  encrypted, and nothing alerts when several fail in a row.
- **`app/import_org.py` went from 0% to 83% covered** (`tests/test_import_org.py`, 30 tests).
  It was the largest hole the new coverage measurement named, and it is the module that parses
  a file an administrator uploads: columns read **by position**, booleans written as words in
  two languages, an import that promises to be safe to re-run against a populated environment.
  Every one of those is a promise the code made and nothing was checking. The tests now hold it
  to all of them, including the round trip nobody had tied together: the blank template the app
  hands out must be readable by the parser that receives it back. They immediately found the
  `Tribu` bug above.
- **End-to-end tests, in a browser, against the real deployment** (`e2e/`, twelve tests,
  [18](docs/18-tests-e2e.md)). They drive the Docker image serving the built SPA and its API in
  front of a real PostgreSQL, not `vite dev` with a stubbed backend, because the bugs that
  justify an end-to-end suite are the ones that only exist once the pieces are assembled: a
  route guard that lets a member open Administration (the API returns 403, but the screen was
  shown), a build shipping a stale chunk, a session cookie the browser refuses to send, a
  dependency upgrade that passes typecheck and build then breaks at runtime. That last one is
  not hypothetical: this suite was written right after the move to React 19 and Vite 8, and it
  is what confirmed the app actually works rather than merely compiles.
  Covered: the login screen and its refusal to say which half of the credentials was wrong,
  logout really invalidating the session server-side, the route guard on a URL typed by hand,
  a tribe created and deleted through the running app, the audit trail recording it and the
  filter finding it, pagination that neither repeats nor skips a row, and a member being
  refused Administration by the navigation, by the URL and by the API.
  A new CI job starts the stack with `docker compose up -d --build`, waits for `/api/health`
  and runs them, publishing the logs and the HTML report as artefacts when it fails.

### Security
- **The shipped defaults are now visible in the product, not only in a log line.** The startup
  guard has warned about a default `SECRET_KEY` or database password since the first hardening
  pass, and that warning is read once, by whoever happened to deploy, and never again.
  **Administration > Ops** now lists every default still in use with the consequence spelled
  out (a default `SECRET_KEY` means anyone can forge a session cookie), and adds three the
  guard never covered: the example break-glass password, a session cookie left unmarked while
  a public URL is configured, and an open `/metrics`. Severity is raised to **critical** when
  `PUBLIC_BASE_URL` is set, which is the honest signal that this is not somebody's laptop -
  a security notice that fires on every developer machine is one everybody learns to ignore.
  Nine tests in `tests/test_insecure_defaults.py`, including the one that matters: a properly
  configured deployment reports nothing at all.
- **`react-router-dom` was vulnerable to an open redirect leading to XSS**
  ([GHSA-jjmj-jmhj-qwj2](https://github.com/advisories/GHSA-jjmj-jmhj-qwj2), plus
  [GHSA-wrjc-x8rr-h8h6](https://github.com/advisories/GHSA-wrjc-x8rr-h8h6): a backslash in a
  `<Link>` target or a `useNavigate` call escaping the app's origin). The whole 6.x line is
  affected and the fix only exists in 7.x, so the router moved to 7.18.2. Nothing in the app
  had to change: it uses `BrowserRouter` / `Routes` / `Link` / `NavLink` / `Navigate` /
  `Outlet` / `useLocation` / `useNavigate` / `useParams` / `useSearchParams`, all unchanged in
  v7. `npm audit` now reports **0 vulnerabilities**, production and development alike.
  Dependabot had not opened a pull request for this one.

### Fixed
- **"Message retention" retained everything.** The setting, offered in Administration >
  Settings as *Message retention (days, 0 = keep all)*, only ever **hid** older posts from the
  listing endpoint. They stayed in the database and in every backup, forever. An administrator
  who set it to satisfy a retention policy had satisfied nothing, and had no way of knowing.
  The hourly purge now really deletes feed posts past the window, along with their replies and
  reactions, through the ORM so the declared cascade runs (the foreign keys have no
  `ON DELETE CASCADE`, so a bulk delete would have failed). **Pinned posts are exempt**:
  pinning is somebody deciding this one stays, which is also how the listing already treated
  them. The admin screen now says plainly that the messages are permanently deleted.
  **Behaviour change**: an instance that already has a non-zero value will start deleting on
  the next scheduler tick. That is what the setting always claimed to do. Eight regression
  tests in `tests/test_retention.py`, where the module had two.
- **The backup sidecar was leaving zero-byte files that counted as backups.** It wrote
  `pg_dump` straight into the final filename, so a failed dump left an empty
  `tribe_AAAAMMJJ_HHMMSS.sql` behind: indistinguishable from a real backup, counted by the
  rotation, and therefore **pushing genuine backups out of the retention window**. Five of them
  were sitting in a running instance. The dump now goes to a temporary file and is published
  only once `pg_dump` has exited 0, the file is non-empty, and it ends with the marker
  PostgreSQL writes at the end of a complete dump; rotation runs only after a success, and only
  over files that really are backups. The success line reports the size, so a glance at the log
  says whether the backup is real.
- **A failed dump skipped the whole day.** The loop slept the full interval after a failure, so
  the usual cause - the database still coming up after a restart, which fixes itself in
  seconds - cost 24 hours of backups, silently. It now retries after `BACKUP_RETRY_SECONDS`
  (5 minutes) and prints the `pg_dump` error.
- **A blank "Annee" cell silently discarded the whole tribe.** The Excel reader dropped any row
  whose **first** cell was empty, which is right for the sheets where the first column is the
  name, and wrong for the `Tribu` sheet where the first column is the year. An administrator
  who left the year blank, a cell the importer is documented to default, got
  `400 : le fichier ne contient pas de tribu` about a file that plainly contained one. The
  `Tribu` sheet is now keyed on the tribe name. And a missing name raises a sentence naming the
  column to fill instead of reaching the database and coming back as an `IntegrityError` on
  `tribes.name`. Found by writing the tests below, which is the whole argument for writing them.
- **The SMTP admin panel was French-only.** Six labels (host, port, username, password, sender
  address, sender name) were hard-coded French strings, so an administrator running the app in
  English read them in French. The CI parity check cannot catch this: it compares the FR and EN
  key sets, and a string that never became a key is in neither. Now translated. A scan of the
  whole frontend found no other case.
- **Every form control in Administration has an accessible name.** Screen-reader users heard
  nothing on most of them: the visible `<label>` was a sibling of its field, never associated
  with it, and the inline editors in the tables have no visible label at all (the column header
  plays that role, which a screen reader reading a single cell never sees). All of them now
  carry the label, taken from the same i18n key so the two can never drift apart. Partial fix,
  and recorded as such in [10](docs/10-tech-debt-and-risk-register.md): the other pages are
  untouched, and clicking a label still does not focus its field, which needs `htmlFor`/`id`.

### Changed
- **`report.py` split: 2440 lines down to 1400.** The four PowerPoint decks moved to
  `reportpptx.py` (890 lines of python-pptx machinery that reads nothing like the HTML
  templating beside it), and the eleven declarations both formats share moved to
  `reportcommon.py`. The dependency runs one way only, `reportpptx` importing `reportcommon`
  and never `report`, and `report` re-exports the deck renderers so no caller had to change.
  Same discipline as below: a seventeen-test surface smoke test was written and run green
  first, and it earned its place immediately by catching two things the plan had missed - the
  roadmap HTML also uses the month labels, and two tests patch the slide cap, which now has to
  be patched on the module that reads it rather than on a re-exported name. Verified further by
  fetching all eight export endpoints from the running container and checking each returns a
  real document.
- **`AdminPage.tsx` split: 3085 lines down to a 152-line shell.** It was one file holding the
  navigation, the permission logic and twenty-five panels covering everything from TLS
  certificates to leave types. The panels now live in `src/pages/admin/`, one module per
  navigation group (`organisation`, `imports`, `configuration`, `authentication`, `oversight`,
  plus `shared` for the two hooks more than one panel needs), and `AdminPage.tsx` keeps only
  what it is: the shell that resolves which tabs a role may open and mounts the active one.
  The refactor was done **after** building the net that catches it, not before: a new
  end-to-end test opens all eighteen sections and asserts each renders without an error banner,
  an empty panel or a console error. It was green before the move and green after, which is the
  only reason a mechanical 3000-line move is defensible. That test stays.
- **Every pending dependency update applied and verified**, closing the thirteen Dependabot
  pull requests that had piled up. Backend: authlib 1.4 to 1.7.2, google-auth 2.38 to 2.56.3,
  PyJWT 2.10.1 to 2.13.0, argon2-cffi 23.1 to 25.1, psycopg2-binary 2.9.12. Frontend: React 18
  to 19.2, react-router-dom 7.18.2 (see above), and a coordinated build-toolchain upgrade -
  vite 5 to 8, vitest 2 to 4 and `@vitejs/plugin-react` 4 to 6 **have to move together**,
  which is exactly why the three separate pull requests could not be merged one by one. Also
  jsdom 25 to 30, `@types/node` 22 to 26, and the GitHub Actions to checkout v7 / setup-node v7
  / setup-python v7.
  React 19 removed the global `JSX` namespace from `@types/react`; three files now import the
  type from the module instead. Two consequences worth knowing: the initial bundle grew from
  317 to 382 KB (117 KB gzipped) between React 19 and router 7, and the production build got
  about three times faster.
  New guard: `tests/test_oidc_client.py` pins the Authlib surface the login actually calls.
  The real OIDC exchange is covered by the Kubernetes bench, which needs a cluster; a rename
  in a future Authlib release would otherwise go unnoticed until somebody clicks "Sign in".
- **Coverage is measured and enforced.** `pytest-cov` with a `fail_under` floor in
  `backend/.coveragerc`, run by the CI backend job. The floor is deliberately a **ratchet**
  set just under what the suite actually reaches (74% of `app/`), not an aspiration: a floor
  above reality fails the build on day one and gets deleted by the first person in a hurry.
  Entry points and one-shot data loaders are excluded, because counting code that is
  exercised by running the app rather than by tests lets real gaps hide behind a comfortable
  percentage. Coverage stays out of `addopts` so a local `pytest` does not pay for it.
  The measurement immediately named the largest genuine hole: `app/import_org.py`, 188
  statements at 0%, which parses an administrator-supplied Excel file. Recorded in
  [08](docs/08-testing-strategy.md). No frontend gate: with eleven unit tests the floor would
  sit at a number that protects nothing, and the real gap there is end-to-end coverage.
- **The audit log is paginated and filterable, and says who acted.** The screen rendered "the
  last 200 entries", which on an instance that has been running for a year answers no question
  at all: what an administrator needs is *who disabled this account* or *what happened on the
  12th*. `GET /api/audit-log` now takes `limit` / `offset` and filters on action (substring,
  case-insensitive), entity, acting user and a date range, and returns
  `{items, total, limit, offset}` - `total` counting the filtered set, so the screen can say
  how much it is not showing. The acting user is resolved server-side into `user_email` /
  `user_name` instead of the bare numeric id the table used to print; it stays null when the
  account has since been deleted, which the nullable foreign key allows on purpose. The admin
  screen gained the matching filter bar, a page size and pagination, with the action box
  debounced so typing does not fire a request per keystroke. **Breaking for any direct API
  consumer**: the response is now an object, not a bare list. Ten regression tests in
  `tests/test_audit_api.py`, where there were none.
- **Doc 16 now teaches the bench instead of listing it.** It assumed minikube, kubectl,
  OpenSSL and Docker were already installed, the scripts already understood, and the purpose
  of each command guessable. Rewritten so nothing is magic: why the bench exists at all (in
  production the app never speaks TLS, so testing SSO on `localhost:8000` proves nothing),
  installation of all five tools per operating system with the command that proves it worked,
  an inventory of the folder before any command is run, `make-pki.sh` explained flag by flag
  so it can be replayed by hand, what `run-tests.py` actually does in seven steps (it was not
  obvious at all that the driver configures the SSO itself through the admin API and resets it
  afterwards), the non-obvious parts of the manifests with the reason each is there, and a
  diagnosis section. The negative control is now three clicks in the admin screen instead of
  an opaque script.

## 2.0 - SSO driven by one public URL, single-port container (2026-08-27)

### Added
- **The Kubernetes/Keycloak bench is now part of the repository** (`bench/k8s-sso/`) with a
  step-by-step tutorial, [16 - Banc Kubernetes de bout en bout](docs/16-banc-kubernetes-sso.md).
  Four manifests, the Keycloak realm, the 18-check driver (`run-tests.py`) and an optional
  access-history seeder reproduce, on any machine, the exact chain the SSO work was validated
  against: app on a single plain-HTTP port behind an Envoy gateway that terminates TLS with an
  internal CA, two public names on one certificate, then a full OIDC login and a full SAML login
  against a real IdP. `make-pki.sh` generates the throwaway PKI, which stays gitignored. The
  app deployment is deliberately the one prescribed by §6.9 of the deployment guide, so running
  the bench also tests the documentation.
- **`backend/scripts/dump_openapi.py`** writes `docs/openapi.json` from the app's routes without
  starting a server, and `--check` fails when the committed snapshot is stale. The CI **Backend**
  job now runs that check on every push, so an unintended contract change surfaces in the pull
  request. The snapshot was already two endpoints behind (`/api/admin/auth-config/test` and
  `/api/access-requests/history`); it is now regenerated and accurate (140 paths). Closes TD-API-1.
- **"Test the connection to the IdP" button**, one per protocol, in Administration →
  Authentification (`POST /api/admin/auth-config/test`, `app/ssotest.py`). Returns an
  ordered list of checks so a failure names the field to fix rather than reporting a
  bare connection error: OIDC discovery, issuer consistency, endpoints, signing keys,
  PKCE, and the client credentials; for SAML, metadata retrieval, IdP entity ID and
  SSO endpoint, signing-certificate expiry, and the SP settings assembled and
  validated by python3-saml exactly as the login path does. It probes what is on
  screen, saved or not, so a change can be checked before it is committed, and it
  signs nobody in. Verified against a live Keycloak, including the failure paths
  (wrong secret, wrong client id, unreachable issuer, unreadable metadata).
- **Access history.** The review screen now shows what has already been handled, not
  only the pending queue (`GET /api/access-requests/history`): SSO arrivals and the
  approve/deny decisions taken on them, newest first, with who decided and where the
  person was placed. Read from the audit trail, the only place recording the author
  of a decision. Gatekeepers see everything; a squad leader sees their own decisions.
- **Milestone-dependency deck (PPTX/HTML).** New export listing every jalon that
  depends on another team, grouped by the entity it waits on. Each line shows the
  jalon, its source squad and tribe, the quarter, the owner and the status. By default
  it keeps only **cross-tribe** dependencies (`mode=cross_tribe`, the real
  coordination points); `mode=all` includes same-tribe and free-text actors. The
  table paginates across slides so no dependency is ever dropped. Available from
  the Export menu ("Dépendances") and via `GET /api/reports/dependencies.pptx`
  (and `.html`), scoped like the other exports (`tribe_id` / `squad_ids` / `year`).

### Changed
- **Version 2.0.0, and the first tagged release.** The project documented its own release
  procedure (bump `backend/app/main.py`, tag `vX.Y.Z`, build the image under that tag,
  `docs/13`) but had never applied it: the version stayed at `1.0.0` while this section grew,
  and the repository had no tag at all, so nothing linked a running container back to a
  commit. The major number reflects the breaking changes below (single-port container, the
  `:8080` redirect listener and `PUT /api/admin/tls-config` removed). `app/ops.py`'s
  `APP_VERSION` default, shown in Admin > Ops, follows, and `docs/openapi.json` was
  regenerated so the published contract announces the same version.
- **One name for the application: TeamFollowUP.** Three coexisted - "Tribe Run Tracker" in the
  README and `package.json`, "Tribe Cockpit" in the backend default `app_name`, the i18n `brand`
  key, the SPA `<title>`, the SMTP sender, the print header, the generated certificates and most
  of the documentation, and "TeamFollowUP" in the repository and the deployment guide. Everything
  now says TeamFollowUP. Existing instances are unaffected: `app_name` is an `AppSetting`, so only
  fresh installs pick up the new default.
- **Documentation figures refreshed against the code**: 289 backend tests over 32 modules (the
  testing strategy still claimed 131 over 13), 11 frontend tests, FR/EN parity on 1132 keys (not
  540), ~17k/~15k lines back/front. The deployment guide's opening summary still said the pod
  "serves HTTPS on :8443, its only port", contradicting §6.9 since the single-port change; it now
  states the port is chosen by `TLS_ENABLED`.
- **SSO configuration is now driven by one public URL.** The OIDC redirect URI and
  the SAML SP entity ID / ACS URL are no longer three absolute URLs to keep in sync
  by hand: they are derived from the app's **public base URL** plus a fixed path
  (`authconfig.derive_sso_urls`). The base URL comes from the new **URL publique**
  field in Administration → Authentification, else `PUBLIC_BASE_URL`, else the
  incoming request (`X-Forwarded-Proto` / `X-Forwarded-Host` are honoured), so a
  local run and any single-hostname deployment need no SSO URL configuration at all.
  Administration → Authentification displays the three resolved URLs ready to copy
  into the IdP; per-URL pinning moved under "Avancé". A pinned URL that merely
  restates the derivation is stored empty, so it keeps following the public URL
  instead of freezing a hostname. `OIDC_REDIRECT_URI`, `SAML_SP_ENTITY_ID` and
  `SAML_ACS_URL` now default to empty (they were `https://localhost:8443/…`, which
  leaked into every fresh install and every `.env` copied from the example).
- **SAML strict-mode validation uses the public URL.** `saml._prepare_request` now
  rebuilds the request from the effective base URL, so the assertion `Destination`
  check compares against the address the browser used and not the pod's internal
  one when a proxy terminates TLS.
- **Documentation and samples realigned on the plain-HTTP model.** `README`, `docs/02`,
  `docs/04`, `docs/06`, `docs/07`, `docs/12`, `docs/13`, `docs/14`, both `.env.example`
  files and `e2e_test.py` referred to `https://localhost:8443` as *the* address; they
  now describe the compose default (plain HTTP `:8000`, TLS terminated upstream) with
  `TLS_ENABLED=true` documented as the standalone alternative. The shipped `.env` also
  had `COOKIE_SECURE=true` against a plain-HTTP listener, which prevents the session
  cookie from being sent at all.

### Fixed
- **`e2e_test.py` asserted the shipped application name.** The check read
  `app_name == "Tribe Cockpit"`, so it broke on the rename and, more importantly, on any
  instance whose administrator had renamed the app, which the setting exists for. It now
  asserts the public config serves a name at all.
- **`LOG_FORMAT` and `LOG_LEVEL` were undocumented**, in neither `.env.example` nor the
  deployment guide's variable table, although `LOG_FORMAT=json` is what makes the logs
  parseable by GCP Cloud Logging and the manifests already set it. Both are now in the two
  `.env.example` files and in the guide's variable table, and `LOG_LEVEL` is passed through
  `docker-compose.yml` like every other knob (only `LOG_FORMAT` was).
- **Saving the auth page froze `PUBLIC_BASE_URL` into the database.** Every save
  of Admin → Authentication persisted the whole config, environment-derived values
  included, so the deployment's `PUBLIC_BASE_URL` became a stored override. After
  any single save, changing it in the manifest or `.env` had no effect and every
  SSO callback URL kept pointing at the previous hostname. The value is now
  persisted only when it actually differs from the environment, so the env var
  stays authoritative until an administrator really types something else. Found
  by moving a running Kubernetes bench from one hostname to another; regression
  tests in `tests/test_authconfig_urls.py`.
- **SAML login was impossible against any IdP that advertises a NameIDFormat**
  (Keycloak, PingFederate). `OneLogin_Saml2_IdPMetadataParser` returns an `sp`
  hint and a `security` block alongside `idp`, and `saml.build_settings` merged
  the whole thing with a flat `dict.update`, replacing our SP section with the
  one-key hint. python3-saml then rejected the settings with
  `sp_entityId_not_found,sp_acs_not_found` and every SAML endpoint answered 500.
  The merge now preserves the values we set and treats the parsed ones as
  suggestions. An IdP asking for signed AuthnRequests is honoured only when an SP
  key pair is configured, instead of making the settings unbuildable. Found by
  driving a real Keycloak from a Kubernetes bench; regression tests in
  `tests/test_saml_settings.py`.
- **Dead setting removed: `PROGRESS_RETENTION_DAYS`.** It referred to the
  `progress_updates` table dropped in migration 0017 and had no effect; removed
  from `config.py`, compose and the `.env` examples. Docs (02/03/07/08/10/11)
  no longer reference `progress.py` / `progress_updates`, and the data-model
  reference now covers all 27 tables (initiatives, OTD, budgets, key messages,
  committees, report baselines, API keys).
- **Dashboard PPTX export no longer silently drops squads.** Multi-squad decks
  were capped at 40 detail slides, so a large selection (e.g. a full org of 130+
  squads) lost every squad past the 40th - the deck came back missing squads like
  "Catalog 12" with no error. The cap is raised well above any realistic squad
  count, and if it is ever exceeded the deck ends with a visible "+N autres
  squads" notice instead of dropping them without a trace. Covered by new
  regression tests plus a randomized loop-mode fuzz harness
  (`backend/tests/fuzz_export_loop.py`).

### Security
- **OTD owner assignment is validated against the tribe (cross-tribe disclosure fix).**
  `POST/PUT /api/otds` accepted an arbitrary `owner_user_id`; a tribe leader could
  assign a squad leader of **another tribe**, who would then see that tribe's OTD
  (title, committed date, budget ref, milestones) through the owner-based
  visibility rule. The owner is now required to be a **squad leader of the OTD's
  own tribe** (`otds._validate_owner`, fail-closed 400 otherwise). Regression test
  in `tests/test_otds.py`.
- **Security review (this branch): no other exploitable issue found.** The keyless
  GCP auth (ADC/WIF/impersonation) keeps TLS verification on (httpx default), the
  `assert_leads_squad` guard is fail-closed, and export responses build their
  `Content-Disposition` filename from integers only. The WIF `external_account`
  config can point its `credential_source` at an admin-chosen URL/file, but that
  endpoint is `require_admin` (same trust level that already controls
  `universe_domain`/`syslog_host`), and executable sources stay disabled unless
  `GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES=1` - no lower-privilege attack path.
- **Keyless GCP authentication for audit-log export (GCS / BigQuery).** The export
  no longer assumes a service-account **JSON key** (a long-lived secret Google
  ranks last and recommends disabling org-wide). A new **auth method** selector in
  **Admin → Logs** offers, keyless-first: **`adc`** (attached service account /
  Workload Identity for GKE - the new default, no secret stored), **`wif`**
  (Workload Identity Federation via an `external_account` config file, for off-GCP
  workloads), **`impersonation`** (base ADC + IAM `generateAccessToken`), and
  **`key`** (the legacy JSON key, kept behind an in-UI warning). Token acquisition
  goes through `google-auth`; the data-plane calls stay on httpx via a small
  transport adapter, so no `requests` dependency is added. A sovereign GCP universe is
  honoured for the STS/IAM endpoints too. Existing key users are unaffected (their
  method stays `key`). New dependency: `google-auth`. See
  [ADR-0012](docs/adr/0012-gcp-auth-keyless.md); infra binding in the deployment
  guide §6.10.a.

### Breaking changes
- **Single-port container, no HTTP→HTTPS redirect listener.** The plain-HTTP :8080
  listener (301 → HTTPS) is removed, along with its admin toggle ("Rediriger HTTP
  vers HTTPS"), the `PUT /api/admin/tls-config` endpoint and the
  `PUBLIC_HTTPS_PORT` variable. Redirection is now exclusively an infrastructure
  concern (e.g. the GKE Gateway API redirect route, `docs/12` §6.9.2); nothing may
  target :8080 anymore.

  The container binds exactly one port, chosen by `TLS_ENABLED`: plain **HTTP
  :8000** (`false`, the recommended model, what compose and the manifests set,
  variables `HTTP_PORT` / `APP_HTTP_PORT`) or **HTTPS :8443** (`true`, the app
  terminating TLS itself, variable `APP_HTTPS_PORT`). Match K8s `containerPort`,
  probe `scheme` and Service `targetPort` to the mode you run (`docs/12` §6.9/§6.10).

## 1.0 - V1 (production-ready)

First delivered version. Built on the initial tribe-steering tool, with the
following additions and a finalization pass.

### Squad content
- **Products & hardware** per squad: one or more product names, plus optional
  hardware names, set on squad **create/edit** (tribe leader / admin, and the
  squad leader for their own squad). Shown at the top of the squad page with the
  squad leader.
- **OTD** - the squad's committed annual objectives are surfaced at the top of the
  squad page (label "OTD"), above the detailed roadmap.
- **Key messages** - curated success / alert / risk notes per squad, timestamped
  (date & time), shown below the roadmap.
- **Governance / comitologie** - optional section (module `committees`, off by
  default) where the squad leader declares the squad's recurring committees
  (name, objective, frequency, day, time, duration, participants, active flag),
  shown as a clean table with a modal editor. Standing (not year-scoped); on the
  squad page and readable by the tribe leader for oversight. Admin toggles it
  from *Services*.
- **Budget tracking** - the tribe leader sets the **total** envelope; the squad
  leader reports **spent** (to date) and **forecast** (projected landing) + a
  comment. Status is derived from forecast (else spent) vs total:
  **on track** (< 90%), **at risk** (90-100%), **over** (> 100%, with overrun
  amount & %). **Visible only** to the admin, the tribe leader, and the squad's
  own leader (enforced server-side; a squad leader never sees another squad's
  budget, and cannot change the total).

### Exports
- Single-squad **HTML export** rendered with the application's own stylesheet and
  component markup, mirroring the squad page exactly (Initiatives → OTD →
  Roadmap → Key messages → Budget), without the global report scaffolding.
- Single-squad **PPTX export** restyled to match (navy header, white rounded
  cards, RAG badges, progress bars), same section order. Budget figures are
  gated to authorized viewers in both formats.

### Administration
- **Redesigned admin navigation**: a grouped left sidebar (Organisation,
  Configuration, Authentification & Email, Modération & Journaux) replacing the
  flat tab bar. Sober, text-only, role-aware (empty groups hidden).

### Security / Transport (HTTPS)
- **Native HTTPS** - the app now terminates TLS itself: HTTPS on **:8443** and an
  HTTP **:8080** listener that 301-redirects to HTTPS (`app/server.py`). No reverse
  proxy required to be secure.
- **Self-signed by default** - a certificate is generated on first boot so the site
  is HTTPS out of the box.
- **Certificate management UI** (Administration → *HTTPS / Certificats*, admin-only):
  import **PEM + key** or **PFX/PKCS#12**, manage **root & intermediate CAs**,
  regenerate self-signed (CN/SAN), toggle HTTP→HTTPS redirect. Changes apply
  **hot** (live `SSLContext` reload) without restarting the container. The DB is the
  source of truth (`AppSetting` key `tls`); the private key is never exposed and all
  changes are audited. Compose now defaults `COOKIE_SECURE=true`.

### Data & operations
- Example organization loaded (Cloud Platform Tribe + product/transverse squads
  with products & hardware). One-shot scripts under `backend/scripts/`
  (`seed_real_org.py`, `prune_users.py`).
- Static `index.html` is served with `Cache-Control: no-cache` so a new build is
  always picked up (no stale SPA after deploy).

### Docs & housekeeping
- New **[Deployment Guide](docs/12-deployment-guide.md)** (VMware, GCP, Sovereign cloud,
  AWS, Azure).
- Untracked compiled artifacts (`__pycache__`/`*.pyc`), removed Office temp lock
  files, hardened `.gitignore`, organized one-shot scripts.

### Migrations
- `0013` squad budget + key messages, `0014` budget forecast,
  `0015` squad products & hardware.
