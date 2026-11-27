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
| **Responsable CS désigné** (la lead CS) | tout dans la rubrique de sa tribe : projets, journal, points à suivre, paramétrage, récaps, diffusions |
| **Contributeur CS**, nommé sur un projet | remplit la fiche, le journal et les points à suivre de ses projets ; ne voit ni les autres projets ni le paramétrage |
| **Lecteur** (capacité `customer_success` d'une persona) | le tableau de bord et les fiches de sa tribe, en lecture |
| Tous les autres | rien : menu absent, API en `403` |

Responsable CS est une **désignation, pas une persona** : elle se cumule avec n'importe
quel rôle.

## 3. Le projet

Les projets sont **à plat** : pas de fiche client ni de fiche offre. Le client et les
personnes sont du **texte libre** (les interlocuteurs n'ont pas de compte dans
l'application).

### 3.1 Champs de la fiche

| Groupe | Champs |
|---|---|
| Identité | titre, client (entité), demandeurs, autres interlocuteurs (texte libre, avec un rôle : sponsor, sécurité, achats, PO...), étiquettes |
| Suivi | étape, météo (vert, orange, rouge, posée à la main), dernier contact (calculé depuis le journal) |
| Offre et livraison | offre (liste paramétrable, ex. TP-GCP for AI), mode (« We do it for you », accompagné), projet GCP cible, livraison prévue et réelle |
| Financier | montant du build (€ HT), devis signé (oui/non), code projet d'imputation, refacturation des consommations (plafond ou sans plafond) |
| Périmètre technique | nombre d'utilisateurs, modèles, classification des données (C1, C2...), durée maximale, **fin d'accès** |
| Jalons | date prévue et date réelle de chaque étape |
| Liens | liens vers les documents (devis, questionnaire de cadrage, demande de dérogation). **Aucun fichier stocké** |
| Champs personnalisés (lot 2) | ajoutés par le responsable CS : texte, nombre, date, liste |

### 3.2 Étapes

Liste par défaut, **modifiable dans le Paramétrage** (noms, ordre, couleurs) :
Demande, Cadrage, Proposition, Accord client, Build, Livré, Clos.

### 3.3 Le journal

Une entrée : **date** (saisie, une date passée est acceptée pour reconstituer
l'historique), **type** (Demande, Décision, Proposition, Livraison, Relance, Blocage,
Note), **personnes** (texte libre), **texte**, liens, et une case **« Dans le récap »**
cochée par défaut pour Décision, Proposition et Livraison. Affiché du plus récent au
plus ancien, filtrable par type. Les décisions vivent ici, sans registre à part.

### 3.4 Les points à suivre

Une seule liste par projet, volontairement simple : **type** (Action, Risque,
Blocage), libellé, porteur (texte libre), échéance, case **réglé**.

- Un **blocage ouvert** fait afficher « Bloqué : dérogation sécurité (S. Soustre)
  depuis le 03/10 » sur la fiche et sur sa carte.
- La **prochaine action** de la fiche est l'action ouverte dont l'échéance est la plus
  proche. On ne la saisit pas deux fois.

## 4. Les écrans

**Tableau de bord** à l'ouverture : projets ouverts, bloqués, livrés sur la période,
montant des builds, puis trois badges calculés (aucune alerte, aucun mail) :

- points à suivre **en retard** ;
- **fin d'accès** à moins de 30 jours ;
- projets ouverts **sans nouvelles** depuis 14 jours (seuil réglable).

Sous les chiffres, les projets, **dans la vue que chacun choisit** et qu'il retrouve
la fois suivante :

| Vue | Lot |
|---|---|
| Cartes, regroupées Bloqués / En cours / Livrés | 1 |
| Kanban par étape (glisser une carte la fait avancer) | 2 |
| Frise : jalons prévus et réels, fin d'accès | 2 |

Chacun règle aussi ce que montrent les cartes, les colonnes et ses filtres
(préférences par utilisateur). Une carte ouvre la **fiche dans une fenêtre** de
l'application, pas dans un onglet.

## 5. Le récapitulatif

Le récap reprend la forme du mail : texte d'introduction, tableau « En résumé », puis
pour chaque projet ses champs clés et les entrées du journal cochées « Dans le récap ».
Les entrées ajoutées depuis le dernier envoi portent la mention « Nouveau ».

- **Copier pour Outlook** (lot 1) : HTML prêt à coller et à retoucher.
- **Diffusion programmée** (lot 2) : par le mécanisme existant des diffusions, avec
  mise en page dans le Studio. Une diffusion porte un **filtre** (offre, étape,
  étiquettes) et un **chapeau** éditable, celui des points communs. On peut en avoir
  plusieurs (un récap TP-GCP for AI, un autre pour une autre offre).

## 6. Reprise de l'existant

- Saisie à l'écran (lot 1), le journal accepte des dates passées.
- **Import Excel** (lot 2) : un classeur modèle (onglets Projets et Journal), à
  télécharger, remplir et réimporter, sur le modèle de l'import Steerco.

Les données de démonstration du dépôt restent fictives et génériques.

## 7. Découpage

| Lot | Version | Contenu |
|---|---|---|
| 1 | 4.2.0 | module, désignations et droits, fiche complète (hors champs personnalisés), étapes paramétrables, journal, points à suivre, tableau de bord et cartes, Copier pour Outlook |
| 2 | 4.3.0 | Kanban, frise, préférences de vue, champs personnalisés, import Excel, diffusions programmées et Studio |

## 8. Où c'est dans le code (lot 1)

| Quoi | Où |
|---|---|
| Droits (responsables, contributeurs, lecteurs) | `backend/app/csaccess.py` |
| Étapes, offres, seuils, texte du récap (par tribe) | `backend/app/csconfig.py`, `app_settings['cs:<tribe_id>']` |
| Routes `/api/cs/*` et le récap HTML | `backend/app/routers/cs.py` |
| Tables | migration `0052_customer_success`, voir [03](03-data-model.md) |
| Écran | `frontend/src/pages/CsPage.tsx`, `frontend/src/components/cs/` |
| Tests | `backend/tests/test_cs.py` |

Pour l'ouvrir : Administration > Modules > Customer Success, puis désigner la lead CS
dans Customer Success > Paramétrage (le tribe leader l'est déjà). Les lecteurs passent
par la capacité « Customer Success (lecture) » d'une persona.

La copie pour Outlook passe par une sélection du HTML rendu et non par l'API
presse-papiers asynchrone : l'application est servie en HTTP derrière le TLS de
l'infrastructure, et cette API n'existe que dans un contexte sécurisé.

## 9. Hors périmètre (décidé)

- fiches client, offre ou contact (texte libre à la place) ;
- registre RAID complet (impact, probabilité) : remplacé par les points à suivre ;
- notifications et mails d'alerte : le tableau de bord suffit ;
- pièces jointes : des liens seulement ;
- lecture d'un mail collé par un LLM.
