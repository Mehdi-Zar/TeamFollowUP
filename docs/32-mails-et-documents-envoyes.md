# 32 - Mails et documents envoyes

Ce que recoit un destinataire, quand, et pourquoi. Ecrit apres trois passes de
controle des mails et des exports PPTX, et apres dix passes sur l'experience de
saisie et de reporting.

## Le corps du mail : un resume, pas le document

Le document complet (HTML) est fait pour un navigateur. Dans une messagerie,
Outlook ignore une partie de sa mise en page, Gmail et Outlook suppriment ses
courbes, un telephone le fait defiler de cote, et Gmail coupe tout message de
plus de 102 Ko. Le mail porte donc un **resume** que toutes les messageries
affichent (tableaux, styles en ligne, 640 px de large, tenus aussi par Outlook) :

- les chiffres cles et la liste des squads, triees par gravite (bloquee, a risque,
  OTD en retard, perimee), avec leur statut, leur avancement et leur derniere
  saisie (en orange quand elle est perimee, en gris « Non renseigne » pour une
  squad qui n'a jamais rien soumis) ;
- pour une seule squad : son statut, son leader, ses messages cles (risques
  d'abord), **ses engagements en retard** (avec la date promise), **ses KPI hors
  cible** (sous tension ou manques, valeur et cible) et les jalons a surveiller :
  les deux signaux qu'un lecteur doit avoir sans ouvrir la piece jointe ;
- l'encart « Nouveautes depuis votre dernier rapport » ;
- un bouton **Ouvrir dans l'application**, quand l'adresse publique de
  l'application est reglee (Administration > Authentification) ;
- une ligne de pied de page qui dit **pourquoi** ce mail arrive et ou le regler.

Le PPTX est joint. Le document HTML complet n'est joint **que** quand le mail n'a
pas de lien vers l'application : les passerelles de securite d'entreprise mettent
souvent les pieces jointes .html en quarantaine. Les pieces jointes sont nommees
« Rapport_hebdomadaire_<perimetre>_<date> ».

La partie texte (celle que montrent les apercus et les messageries sans HTML)
reprend ce resume. Les mails portent les en-tetes attendus d'un robot (Date avec
fuseau, Message-ID, Auto-Submitted, qui evite les boucles de reponses d'absence).

## Verifie de bout en bout

`backend/tests/test_e2e_reporting_to_inbox.py` joue le parcours complet : un squad
leader saisit sa semaine (jalons avec dependances vers une squad, une tribe et un
texte libre, un engagement, un KPI, un message cle, le moral, le commentaire du
trimestre) et l'envoie ; tous les exports sont produits (rapport hebdo, tableau de
bord, roadmap, dependances, roadmap d'une squad, Steerco, initiatives,
organigramme ; HTML et PPTX ; francais et anglais) ; puis chaque mail part par une
**vraie connexion SMTP** vers un serveur local qui le garde (envoi manuel, rapport
planifie, bouton Tester, envoi aux squad leaders, abonnement, avis de modification,
acces valide, test SMTP). Chaque document et chaque mail est relu comme son lecteur
le recoit (PPTX ouvert, HTML reduit a son texte visible, mail analyse comme par une
messagerie, pieces jointes ouvertes) : ce qui a ete saisi doit y etre, aucune valeur
parasite (None, undefined, NaN, « {x} »), ni tiret cadratin ni point median.
`E2E_OUT=<dossier>` y ecrit tous les documents et mails pour les regarder.

## Quand partent les mails

| Mail | Declencheur | Destinataires |
|---|---|---|
| Rapport programme | le jour et l'heure choisis, **heure de Paris** | liste fixe, un mail par squad, leaders de chaque squad, recapitulatif de tribu (leaders de squad en copie) : chaque adresse recoit un document une seule fois |
| Abonnement personnel | le jour et l'heure choisis, heure de Paris | l'abonne ; objet « Rapport \| perimetre \| semaine 39 » |
| Envoi immediat | bouton d'export | l'adresse saisie ; une version passee porte sa date dans l'objet, le fichier et le corps |
| Avis de modification | **la soumission du reporting** (par defaut), et au choix chaque type de modification | liste fixe, tribe leader, leaders de la squad ; **jamais l'auteur** |
| Fil | nouveau message, reponse | qui suit le fil (Preferences) |
| Acces | demande d'acces ; acces valide ou refuse | les validateurs (limites a la tribu quand elle est connue) ; la personne elle-meme |

### Avis de modification

- Par defaut, seule la **soumission** previent : c'est le moment ou la squad dit
  que son reporting est pret. Les modifications peuvent etre ajoutees une par une.
- Les modifications rapprochees sont **regroupees** : un seul mail part quand la
  squad n'a plus rien modifie depuis le delai choisi (15 minutes par defaut), avec
  toutes les modifications et tous leurs auteurs. 0 = un mail par modification.
- Le mail dit qui, quoi et quand (heure de Paris), puis ce qui a change depuis
  l'avis precedent (jalon passe de « A risque » a « Livre », etc.).

## Quand le serveur de mails ne repond pas

- **Rapport programme** : si tous les envois echouent, rien n'est marque comme
  fait ; le planificateur reessaie a l'heure suivante et l'encart « Nouveautes »
  ne perd pas la semaine.
- **Avis de modification** : un avis refuse retourne dans la file et repart au
  passage suivant du planificateur (48 essais au plus).
- **Boutons de test** (SMTP, rapport, avis) : la raison de l'echec est affichee.
- **Envoi aux squad leaders** : les squads dont le mail a ete refuse sont listees.

## Les documents PPTX

- La synthese continue sur des slides « (suite) » au lieu de cacher des squads ;
  elle a une colonne « Derniere saisie » et trie par gravite.
- Chaque slide est datee ; une version passee le dit sur chaque slide
  (« Version du 22/08/2026 ») et nomme les squads sans saisie a cette date.
- Aucun texte sous 8 pt : un texte trop long est coupe sur un mot entier avec
  « … », jamais au milieu d'un mot quand on peut l'eviter.
- Le deck hebdomadaire se termine par une slide « Points d'attention » (squads a
  surveiller, engagements de tribu sans squad, absences quand le module est actif).
- Roadmap : noms de squad lisibles, statut de chaque jalon, les plus graves d'abord.
- Organigramme : legende, date, traits a angle droit, une squad jamais saisie en gris.
- Steerco : le PPTX suit la plateforme choisie a l'ecran, comme le HTML.
