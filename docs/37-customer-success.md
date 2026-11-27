# 37 - Customer Success : suivre les projets qu'on livre (cadrage)

> Statut : lot 1 livré en 4.2.0 (2026-11-27) ; le lot 2 (4.3.0) reste à faire, voir la section 7.
> Décision d'architecture : [ADR 0020](adr/0020-customer-success-module.md).

## 1. Le besoin

La lead Customer Success suit aujourd'hui ses projets dans OneNote et dans des mails.
Le mail récapitulatif qu'elle (ou son manager) envoie régulièrement en montre la forme :

- un tableau **« En résumé »** : sujet, demandeur, projet GCP, statut ;
- des **points communs** à tous les sujets (classification, dérogation sécurité,
  refacturation des tokens) ;
- pour chaque sujet, une **chronologie datée** : demande, accord, conditions,
  proposition chiffrée, livraison, relances, blocages ;
- des **blocages** qui durent (une dérogation sécurité en instruction depuis des semaines).

La rubrique **Customer Success** remplace OneNote pour la saisie et produit ce mail
au lieu de le réécrire à la main.

## 2. Qui fait quoi

Module optionnel `customer_success`, **désactivé par défaut** (Administration >
Modules). Même modèle que le Steerco (ADR 0018 et 0019).

| Qui | Ce qu'il peut faire |
|---|---|
| **Administrateur** | tout, dans toutes les tribes |
| **Tribe leader** | responsable CS de sa tribe **par défaut** ; désigne et retire les autres responsables CS |
| **Responsable CS désigné** (la lead CS) | tout dans la rubrique de sa tribe : projets, journal, points à suivre, récaps, diffusions |
| **Contributeur CS**, nommé sur un projet | remplit la fiche, le journal et les points à suivre de ses projets ; ne voit ni les autres projets ni les responsables |
| **Lecteur** (capacité `customer_success` d'une persona) | le tableau de bord et les fiches de sa tribe, en lecture |
| Tous les autres | rien : menu absent, API en `403` |

Responsable CS est une **désignation, pas une persona** : elle se cumule avec n'importe
quel rôle.

## 3. Le projet

Les projets sont **à plat** et la fiche est courte : seulement ce qui sert au suivi. L'offre, les étiquettes, les autres interlocuteurs, les jalons par étape, les modèles, la classification, la durée maximale, le mode de livraison, le projet GCP, le nombre d'utilisateurs et la refacturation des consommations de la 4.2.0 ont été retirés. Le client et les
personnes sont du **texte libre** (les interlocuteurs n'ont pas de compte dans
l'application).

### 3.1 Créer, puis mettre à jour

Deux fenêtres distinctes, pour ne jamais montrer à la création ce qui n'existe pas
encore (historique, points à faire, facturation) :

- **Créer** : « Nouveau projet » ouvre une petite fenêtre avec seulement ce que dit la
  demande : titre, client, demandeurs, description et, s'ils sont connus, le prix
  (€ HT) et la livraison souhaitée. Le prix démarre « À facturer ». Un titre suffit. Après « Créer le projet », on revient au tableau : la
  ligne du projet est marquée et un message propose **Compléter maintenant**, sans
  obligation.
- **Mettre à jour** : le bouton **Mettre à jour** au bout de chaque ligne du tableau
  (« Voir » en lecture seule) ouvre le projet dans une **fenêtre guidée**, la
  même que pour configurer une squad ou remplir un rapport Steerco : les étapes à
  gauche, chacune avec ce qu'elle contient déjà (coche quand elle est remplie),
  Précédent et Suivant en bas. Les champs sont posés à plat, sans cadre dans la
  fenêtre. La fiche est **enregistrée à chaque changement d'étape et à la fermeture**.

| Étape | Champs |
|---|---|
| Le projet | titre, description, client (entité), demandeurs, liens vers les documents (**aucun fichier stocké**) |
| Avancement | étape, statut (En bonne voie, À surveiller, En difficulté ; la couleur en découle), livraison prévue, **date de livraison** |
| Facturation | prix (€ HT), **remise** facultative en % ou en € (le prix net s'affiche dessous ; la remise se saisit aussi à la création), code d'imputation, et où en est la facturation : **À facturer**, **Facturé** (en attente de paiement), **Payé** |
| Suivi | deux tableaux. **À faire** : type (action, risque, blocage), quoi, qui, échéance, une case à cocher une fois réglé (les réglés se masquent). **Historique** : date, type, ce qui s'est passé, dans le récap ou non. Chaque tableau a sa **ligne d'ajout en haut**, et chaque ligne se modifie sur place (voir 3.3 et 3.4) |
| Champs personnalisés (lot 2) | ajoutés par le responsable CS : texte, nombre, date, liste |

### 3.2 Étapes

Liste fixe, sans réglage à faire : Demande, Cadrage, Proposition, Accord client, Build,
Livré, Clos (les deux dernières valent « terminé »). Les seuils des alertes gardent aussi
leur valeur par défaut : 14 jours sans nouvelles.

### 3.3 L'historique (ce qui s'est passé)

Une entrée : **date** (saisie, une date passée est acceptée pour reconstituer
l'historique), **type** (Demande, Décision, Proposition, Livraison, Relance, Blocage,
Note), **texte**, et une case **« Dans le récap »** cochée par défaut pour Décision,
Proposition et Livraison. Affiché du plus récent au plus ancien. Les décisions vivent ici, sans registre à part.

### 3.4 À faire (ce qui reste à faire ou bloque)

Une seule liste par projet, volontairement simple : **type** (Action, Risque,
Blocage, Note), quoi, qui, échéance, case **réglé**. Une note est à garder en tête :
elle n'est ni la prochaine action ni un blocage. Les points réglés sont masqués, un clic
les montre.

- Un **blocage ouvert** fait afficher « Bloqué : dérogation sécurité (depuis 14 j) »
  dans le tableau des projets.
- La **prochaine action** de la fiche est l'action ouverte dont l'échéance est la plus
  proche. On ne la saisit pas deux fois.

## 4. Les écrans

**Une bande de chiffres** à l'ouverture, sans tuiles : par défaut projets ouverts,
bloqués, montant à facturer et montant en attente de paiement. **Personnaliser** en ajoute
d'autres : points en retard, projets sans nouvelles depuis 14 jours (seuil réglable),
livrés dans l'année, montant facturé en attente de paiement, montant payé. Aucun ne déclenche d'alerte
ni de mail. Ceux qui comptent des projets sont **cliquables** et filtrent le tableau.

Sous les chiffres, les projets, **dans la vue que chacun choisit** et qu'il retrouve
la fois suivante :

| Vue | Lot |
|---|---|
| Tableau triable, **une ligne par projet** : projet, client (entité), demandeurs, étape, statut, blocage ou prochaine action (avec son échéance), dernier échange ; en option la livraison et le prix. Un texte trop long est coupé, son texte entier s'affiche au survol. Les bloqués en tête, les livrés et clos grisés (masquables) ; jamais de défilement horizontal | 1 (remplace les cartes de la 4.2.0) |
| Kanban par étape (glisser une carte la fait avancer) | 2 |
| Frise : jalons prévus et réels | 2 |

Au-dessus du tableau, une recherche et des **filtres** : étape, client, statut, livrés
et clos. **Personnaliser** permet à chacun de choisir ses chiffres et ses colonnes, et
l'ordre des colonnes : on les glisse dans la liste, ou directement par leur en-tête
dans le tableau. Le choix est gardé dans le navigateur. Le bouton Mettre à jour, au bout de chaque ligne, ouvre le projet dans sa fenêtre guidée (3.1) ; un clic ailleurs sur la ligne ne fait rien.
L'écran reste sobre : pas de pastilles ; l'étape et le statut s'écrivent en toutes
lettres, le statut dans sa couleur, et le reste n'est coloré que pour une alerte
(une date de dernier échange trop ancienne, un montant pas
encore payé, en orange ; un blocage, en rouge).

### 4.1 Exporter

Le bouton **Export** de CS > Projets, le même que sur le Dashboard et la Roadmap, donne
la liste en **HTML** (aperçu dans l'application), **JPG**, **PPTX** et **Slides**. Le
document reprend les quatre chiffres (projets ouverts, bloqués, à facturer, facturé en
attente de paiement), puis une ligne par projet : les bloqués d'abord, puis les ouverts
par étape, les livrés et clos à la fin. Les montants sont des prix nets.

Le PowerPoint passe par le Studio (document **Customer Success**) : gabarit, masque et
thème de la tribe, nombre de lignes par slide, projets livrés et clos masqués ou non.
Routes : `GET /api/cs/export.html` et `GET /api/cs/export.pptx` (code : `app/csreport.py`).

## 5. Le récapitulatif

Le récap reprend la forme du mail : texte d'introduction, tableau « En résumé », puis
pour chaque projet ses champs clés et les entrées du journal cochées « Dans le récap ».
Les entrées ajoutées depuis le dernier envoi portent la mention « Nouveau ».

- **Copier pour Outlook** (lot 1) : HTML prêt à coller et à retoucher.
- **Diffusion programmée** (lot 2) : par le mécanisme existant des diffusions, avec
  mise en page dans le Studio. Une diffusion porte un **filtre** (étapes)
  et un **chapeau** éditable, celui des points communs.

## 6. Reprise de l'existant

- Saisie à l'écran (lot 1), le journal accepte des dates passées.
- **Import Excel** (lot 2) : un classeur modèle (onglets Projets et Journal), à
  télécharger, remplir et réimporter, sur le modèle de l'import Steerco.

Les données de démonstration du dépôt restent fictives et génériques.

## 7. Découpage

| Lot | Version | Contenu |
|---|---|---|
| 1 | 4.2.0 | module, désignations et droits, fiche complète (hors champs personnalisés), étapes paramétrables, journal, points à suivre, tableau de bord et tableau des projets, Copier pour Outlook |
| 2 | 4.3.0 | Kanban, frise, champs personnalisés, import Excel, diffusions programmées et Studio |

## 8. Où c'est dans le code (lot 1)

| Quoi | Où |
|---|---|
| Droits (responsables, contributeurs, lecteurs) | `backend/app/csaccess.py` |
| Étapes, seuils, texte du récap (par tribe) | `backend/app/csconfig.py`, `app_settings['cs:<tribe_id>']` |
| Routes `/api/cs/*` et le récap HTML | `backend/app/routers/cs.py` |
| Tables | migrations `0052_customer_success` et `0054_cs_simplify`, voir [03](03-data-model.md) |
| Écran | `frontend/src/pages/CsPage.tsx`, `frontend/src/components/cs/` |
| Tests | `backend/tests/test_cs.py` |

Pour l'ouvrir : Administration > Modules > Customer Success, puis désigner la lead CS
dans Customer Success > Responsables (le tribe leader l'est déjà). Les lecteurs passent
par la capacité « Customer Success (lecture) » d'une persona.

La copie pour Outlook passe par une sélection du HTML rendu et non par l'API
presse-papiers asynchrone : l'application est servie en HTTP derrière le TLS de
l'infrastructure, et cette API n'existe que dans un contexte sécurisé.

## 9. Hors périmètre (décidé)

- fiches client ou contact (texte libre à la place), notion d'offre ;
- registre RAID complet (impact, probabilité) : remplacé par les points à suivre ;
- notifications et mails d'alerte : le tableau de bord suffit ;
- pièces jointes : des liens seulement ;
- lecture d'un mail collé par un LLM.
