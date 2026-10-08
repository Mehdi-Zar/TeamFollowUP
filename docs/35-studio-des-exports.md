# 35 - Le Studio des exports : mettre en page les documents, par portée

> Livré en **3.0.0**. Ce document décrit ce qui existe. La proposition qui l'a
> précédé, et ses décisions, sont résumées en fin de document (section 11).

Tous les documents PowerPoint de l'application (tableau de bord, rapport hebdo,
roadmap, dépendances, initiatives, steerco, organigramme) passent maintenant par
un **modèle**. Un modèle dit ce que montre le document et dans quel ordre ; il
s'applique à l'organisation, à une tribe, à une squad ou à une plateforme ; il se
règle dans l'application, avec un aperçu sur les vraies données.

Sans aucun modèle assigné, un document sort **à l'octet près** comme avant :
le modèle « Standard » de chaque document reproduit le deck d'origine, et un test
le vérifie (`test_standard_templates_render_the_legacy_decks_to_the_xml`).

## 1. Où ça se trouve

**L'usage courant tient en trois gestes.** Le Studio s'ouvre sur « Mes documents » :
une carte par document, la mise en page qu'il utilise, et un bouton **Modifier**.
L'éditeur simple montre les slides dans l'ordre : une case pour l'afficher, deux
flèches pour la déplacer, un clic pour voir dessous ce qu'elle montre et ses
réglages ; des boutons ajoutent une page de garde, un texte, une slide libre ou
une slide PowerPoint. L'aperçu est à droite. **Enregistrer et appliquer**
enregistre, publie et assigne à la portée choisie en un seul clic : il n'y a plus
de modèle à créer, publier puis assigner à la main.

Tout le reste (modèles, assignations, thèmes, fichiers, versions, verrous,
héritage) est sous **Gestion avancée** et **Éditeur avancé**.


- **Studio des exports** (menu de gauche), ouvert par persona : capacité « Studio
  des exports » dans Administration > Personas, cochée par défaut pour
  l'administrateur et les tribe leaders (à cocher pour les squad leaders si on
  veut qu'ils règlent la mise en page de leur squad). Ce que chacun y change
  suit ensuite son rôle (section 3).
- **Menu Exporter**, sur chaque document : un bouton **Slides**, le PowerPoint
  lui-même affiché dans l'application, tel que son modèle le met en page.

## 2. Les notions

| Notion | Ce que c'est |
|---|---|
| Section | Une slide, ou une par squad, ou une par plateforme : synthèse, slide de squad, points d'attention, roadmap, dépendances, initiatives, slide de plateforme, organigramme, et les sections génériques (page de garde, texte libre, mise en page libre, slide PowerPoint importée) |
| Bloc | Une partie d'une section, qu'on masque ou qu'on règle : l'en-tête, le moral, la frise, les messages clés, le budget, la légende, une colonne du tableau, un panneau du one-pager steerco... |
| Mise en page libre | Une grille de 12 colonnes sur 8 rangées où l'on place des blocs (texte, image, compteurs, tableau des squads, frise d'une squad, panneaux steerco...), une fois ou une slide par squad ou par plateforme |
| Thème | Le masque PowerPoint (pris dans la bibliothèque de fichiers), douze couleurs, une police et sa taille |
| Modèle | Un thème, des réglages du document (nom du fichier, pied de page, numéros de slide) et des sections dans un ordre |
| Assignation | Quel modèle une portée utilise pour un type de document |

Les textes acceptent des champs : `{doc}`, `{scope}`, `{year}`, `{date}`, `{app}`,
`{squad}`, `{leader}`, `{platform}`, `{period}`, `{version}`, `{page}`.

## 3. Qui fait quoi

| Rôle | Peut |
|---|---|
| Administrateur | Tout, à toutes les portées, y compris l'organisation entière |
| Tribe leader | Les modèles, thèmes et fichiers de sa tribe, de ses squads et de ses plateformes, en mode complet |
| Squad leader | Le modèle d'une squad qu'il dirige, en **mode simple** : il masque, règle et réordonne ce que le modèle de la tribe contient, il n'ajoute rien |
| Tout le monde | Exporter et voir les slides, avec la mise en page de sa portée |

Le serveur applique ces règles (`exportstore.can_design`, `simple_only`), l'écran
ne fait que les montrer. Un modèle Standard ne se modifie pas : on en dérive un.

## 4. Héritage, verrous, résolution

- **Résolution** : un document prend le modèle de la portée la plus proche : la
  squad, puis sa tribe, puis l'organisation, puis Standard. Une slide steerco
  regarde d'abord sa plateforme.
- **Suivre ou copier** : un modèle « suit » son modèle source (seuls ses écarts
  sont gardés, et les évolutions du parent lui parviennent), ou en est une **copie
  indépendante**. « Ne plus suivre le parent » transforme le premier en second sans
  rien changer à ce qu'il produit.
- **Verrous** : un modèle peut verrouiller sa page de garde, une section, un bloc,
  le thème, l'ordre ou l'ajout de sections. Les modèles qui le suivent ne peuvent
  plus y toucher ; leurs écarts sur une partie verrouillée sont ignorés **et
  affichés** dans l'éditeur, jamais effacés en silence. Même chose pour un écart
  sur une section que le parent a retirée.
- **Document consolidé** : la slide de chaque squad d'un document de tribe suit le
  modèle de la tribe ; la case « Prendre la slide de chaque squad quand elle a son
  modèle » fait l'inverse, section par section. Idem par plateforme pour le steerco.
- **Brouillon et publication** : on enregistre un brouillon ; les exports, les
  envois planifiés et les modèles qui suivent celui-ci utilisent la **version
  publiée**. Chaque publication est une version : on compare deux versions, ou le
  brouillon avec le parent, et on restaure une version ancienne.

## 5. L'aperçu, et les contrôles

L'aperçu n'est pas un second rendu : le serveur construit le PowerPoint que
l'export enregistrerait, puis le lit (formes, textes, tableaux, graphiques, images,
décorations du masque) et l'écrit en pages HTML positionnées
(`app/pptxhtml.py`). La géométrie est donc celle du fichier ; seul le texte est mis
en page par le navigateur, ce qui peut décaler une coupure de ligne d'un mot.

En le lisant, il relève ce qu'une slide projetée ne supporte pas : un texte sous
8 points, un texte qui déborde de sa forme, un texte trop pâle sur son fond (moins
de 3:1), et les deux caractères que le dépôt n'imprime jamais. Chaque alerte mène
à sa slide. Le Studio refuse ces deux caractères à la saisie.

L'aperçu tourne sur les données choisies (une tribe, une squad, une plateforme,
une version datée, une langue), derrière **les mêmes contrôles d'accès que
l'export** : un modèle décide de la mise en page, jamais de ce qu'on peut lire.

## 6. Fichiers

Masques PowerPoint, slides à importer et images (PNG, JPEG, GIF), 12 Mo au plus,
reconnus par leur contenu et non par leur nom. Un `.pptx` est vérifié comme
archive avant d'être ouvert (nombre d'entrées, taux de compression), les
présentations avec macros sont refusées. Une slide importée garde ses formes, ses
images et son fond, ses champs remplis ; ses graphiques et objets incorporés ne
sont pas repris, et l'aperçu le dit.

Le gabarit de Administration > Import reste le masque du thème Standard.

## 7. Import et export d'un modèle

« Exporter le fichier du modèle » produit un JSON (spécification, thème, fichiers
utilisés en base64). « Importer un fichier de modèle » le recrée ailleurs, tout
étant revalidé comme une saisie : c'est le chemin pour préparer un modèle en test
puis le passer en production, qui n'a pas d'accès à la base.

## 8. Architecture

| Module | Rôle |
|---|---|
| `exportspec.py` | Catalogue (sections, blocs, paramètres, widgets), modèles Standard, validation, héritage par différence (`diff`, `apply`) et verrous. Pur, sans base |
| `exportengine.py` | Construit un deck depuis une spécification ; reçoit ses données par des fournisseurs, préparés par les routes d'export |
| `exportblocks.py` | Page de garde, texte libre, grille, slide importée, pied de page |
| `reportpptx.py`, `routers/steerco.py`, `orgrender.py` | Les renderers d'origine, découpés en sections et en blocs dessinables dans un cadre |
| `exportstore.py` | Modèles en base, droits, résolution, thèmes, fichiers, rendu d'un export |
| `pptxhtml.py` | L'aperçu HTML lu depuis le deck, et les contrôles |
| `routers/exports.py` | L'API `/api/exports` |

Les routes d'export existantes (`/api/reports/*.pptx`, `/api/steerco/document.pptx`,
`/api/org/export.pptx`, `/api/initiatives/report.pptx`, la roadmap d'une squad) et
les envois par mail résolvent le modèle de leur portée ; elles acceptent en plus
`template_id` (un modèle partagé).

## 9. Données

Tables `export_assets`, `export_themes`, `export_templates`,
`export_template_versions`, `export_assignments` (migration
0043). Un modèle dérivé stocke un patch par identifiants de sections et de blocs,
jamais par position. Voir [03](03-data-model.md).

## 10. Limites connues

- Un texte de l'aperçu peut couper sa ligne un mot plus tôt ou plus tard que
  PowerPoint (police du poste).
- La frise d'une squad placée dans une zone étroite d'une mise en page libre range
  les titres d'engagement par trimestre et ne relie plus les boîtes à leur mois
  par un trait : il traverserait ces titres.
- Le HTML d'origine (corps des mails, bouton HTML) n'est pas piloté par les
  modèles ; le bouton « Slides » montre, lui, le deck mis en page.

## 11. Décisions prises

Les six questions de la proposition ont été tranchées ainsi : le squad leader
conçoit en mode simple sur un modèle qui suit celui de sa tribe ; le document
consolidé suit le modèle de la tribe, avec une option par section pour la slide de
chaque squad ; un écart orphelin est ignoré et signalé, jamais supprimé ; le HTML
d'origine reste tel quel, le deck se voit en slides dans l'application ; les
modèles publiés se partagent entre tribes ; l'import et l'export en fichier
existent. Voir l'[ADR 0017](adr/0017-templates-drive-the-renderers-and-the-preview-reads-the-deck.md).
