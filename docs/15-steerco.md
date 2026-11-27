# 15 - Steerco (comite de pilotage) : un sujet a part

Le module **Steerco** produit, pour le comite de pilotage, un **one-pager KPI par
plateforme** (HTML / PPTX) construit automatiquement a partir d'instantanes mensuels.
On saisit des **valeurs brutes** ; tout le reste (variation vs M-1, couleurs SLA,
graphiques de l'annee) est **calcule au rendu**, jamais tape a la main.

Module optionnel, **desactive par defaut** : Administration -> Modules -> `steerco`.

Depuis la version 4.0 le Steerco est **un sujet a part**, sorti du reporting
hebdomadaire ([ADR 0018](adr/0018-steerco-is-a-topic-of-its-own.md)) : un menu
**Steerco** a lui, mene par des **Steerco leaders**, avec un cycle de validation. La
facon de remplir un mois (l'assistant en cinq etapes, les douze mois a cote de la
colonne a remplir) n'a pas change.

## 1. Qui fait quoi

| Qui | Ce qu'il peut faire |
|---|---|
| **Administrateur** | tout, dans toutes les tribes ; seul a retirer au tribe leader sa designation par defaut |
| **Tribe leader** | Steerco leader de sa tribe **par defaut** (il reste tribe leader) ; designe et retire les autres Steerco leaders de sa tribe |
| **Steerco leader designe** | tout dans le Steerco de sa tribe : plateformes, modele, saisie, import, validation, reouverture, rappel, envoi de la presentation, mise en page de ses plateformes dans le Studio. Il ne designe personne |
| **Lecteur** (capacite `steerco` d'une persona) | l'onglet Reporting du mois de sa tribe, en lecture : etats, apercus et documents |
| Tous les autres | rien : le menu n'apparait pas, l'API repond `403` |

Steerco leader est une **designation, pas une persona** : elle se cumule avec
n'importe quel role (un squad leader peut etre Steerco leader de sa tribe). Elle est
stockee dans la table `steerco_leaders` (`user_id`, `tribe_id`, `excluded`). Le tribe
leader n'y a pas de ligne : il l'est implicitement, et une ligne `excluded` (posee par
l'administrateur seulement) le lui retire. Les regles vivent dans
`backend/app/steercoaccess.py`, et `/api/auth/me/permissions` renvoie a l'interface ce
que l'utilisateur peut faire (`steerco: {read, run, run_tribe_ids, read_tribe_ids,
designate_tribe_ids}`).

La capacite `steerco` se coche dans **Administration > Personas** ; elle est fermee par
defaut pour toutes les personas sauf l'administrateur. Une squad, ses leaders et ses
contributeurs **ne saisissent plus rien** dans le Steerco : la propriete element par
element des versions 3.x a disparu.

## 2. Le menu Steerco : le reporting d'un cote, le parametrage de l'autre

Deux onglets, pour que le travail du mois et les reglages ne se melangent jamais :

| Onglet (FR / EN) | Pour qui | Contenu |
|---|---|---|
| **Reporting du mois** / Monthly report | Steerco leaders et lecteurs | le mois choisi en trois etapes numerotees, l'une sous l'autre ; une bascule **Vue annuelle** montre le tableau plateformes x mois |
| **Parametrage** / Settings | Steerco leaders, administrateur, tribe leader | tous les reglages, au meme endroit, avec une liste de mise en place |

**Reporting du mois.** Les trois etapes, dans l'ordre ou on les fait :

1. **Remplir les chiffres des plateformes** : la liste des plateformes est dans
   l'etape elle-meme. Chacune a son etat (A remplir, En cours, Remplie a valider,
   Validee) et son bouton **Remplir** (puis **Continuer**, puis **Consulter**), qui
   ouvre l'assistant a l'ecran. **Voir la diapositive** la deplie telle qu'elle sera
   exportee. Sous la liste, l'alternative : **Importer un fichier Excel**.
2. **Valider les chiffres** : **Valider tout ce qui est rempli**, ou plateforme par
   plateforme a la fin de l'assistant.
3. **Envoyer la presentation** : grise tant que tout n'est pas valide ou qu'il n'y a
   pas de destinataire, avec la raison et un lien vers le Parametrage.

L'etape a faire est mise en avant et chacune dit ou on en est (« 3 sur 5 remplies »).
Tant que la tribe n'a aucune plateforme, l'onglet renvoie vers le Parametrage. Un
lecteur voit la liste et les diapositives, sans les etapes.

**Parametrage.** Une liste **Parametrage du Steerco** donne, dans l'ordre ou on les
fait la premiere fois, chaque reglage avec son etat et un bouton vers sa section :

1. **Les Steerco leaders** (voir 1) ;
2. **Les indicateurs communs (KPI et SLA)** que reprend chaque plateforme ;
3. **Les plateformes (une diapositive chacune)** : leurs lignes, leurs squads
   concernees, le **type de graphique KPI**, et **Modifier la mise en page (Studio)** ;
4. **Le rappel et les destinataires** de la presentation ;
5. **Les lecteurs (facultatif)** : ce reglage vit dans Administration > Personas
   (capacite « Steerco (lecture) ») ; la section l'explique et y mene.

Les deux reglages tenus ailleurs (la lecture, par persona ; la mise en page, dans le
Studio) sont nommes ici avec leur chemin. Le module lui-meme s'allume dans
Administration > Modules.

**Vocabulaire.** Les libelles evitent le jargon : une **plateforme** = une
**diapositive** ; l'ensemble des diapositives du mois = la **presentation** (et non
« pack » ou « one-pager ») ; **Remplir** et non « Saisir ». L'anglais est ecrit pour
des lecteurs dont ce n'est pas la langue maternelle : des mots proches du francais
(*data*, *presentation*, *validate*, *complete*, *modify*), pas d'expressions
idiomatiques ni de verbes a particule (*figures*, *deck*, *fill in*, *run*, *lay out*).

Une personne qui mene plusieurs tribes (l'administrateur) choisit la tribe dans la barre
du haut ; le choix est retenu. Le Steerco n'a plus d'etape dans la Saisie
hebdomadaire, plus d'onglet dans le tableau de bord ni dans Initiatives, plus de
section dans Mes squads, et Administration > Plateformes a disparu. Les anciens liens
(`/?tab=steerco`, `/steerco?tab=consolidation`, `?tab=leaders`...) menent au bon onglet.

## 3. Une plateforme, une diapositive

L'unite de reporting est la **plateforme**, pas la squad. La plateforme porte le
**gabarit** de sa diapositive (`platforms.template`) : les cartes KPI (et leurs
sous-metriques), les colonnes SLA, et le rendu du graphique. Le compteur d'incidents et
les evenements sont toujours presents.

```json
{"kpis": [{"label": "K8aaS", "sub": ["GitLab"]}],
 "sla":  [{"label": "Gitlab"}],
 "display": {"kpi_chart": "auto", "chart_kpis": []}}
```

L'instantane mensuel (table `steerco_entries`, unique sur `(platform_id, period)`,
`period` au format `AAAA-MM`) est **positionnel** par rapport au gabarit :
`data["kpis"][i]` porte la valeur de `template["kpis"][i]`.

```json
{"kpis": [{"label": "Cloud Users", "value": "247"}],
 "sla": {"services": ["Incidents", "Gitlab"], "cells": [{"v": "99,4%"}]},
 "incidents": "13",
 "last_events": [{"date": "12/07", "tag": "Incident", "text": "...", "sev": "amber"}],
 "next_events": []}
```

A l'enregistrement, le serveur **reconstruit le squelette depuis le gabarit** et ne
reprend du payload que les valeurs (`app/platforms.py:merge_values`) : un onglet reste
ouvert ne peut pas renommer une ligne de la diapositive.

Les **squads concernees** d'une plateforme sont **facultatives** (table
`platform_contributors`, champ `squad_ids` de l'API ; `contributor_ids` reste accepte).
Elles servent a deux choses : proposer leurs messages cles dans l'etape evenements, et
afficher la plateforme, en lecture, sur la page de la squad.

Sous charge, le document PowerPoint ne coupe rien : ce qu'un panneau ne tient
pas (KPI, SLA, evenements) part en entier sur une **slide de detail** de la
plateforme, et le panneau le dit (« +N autres en slide suivante »). Voir
`24-exports-frise-annuelle-et-moral.md`, section 8 ter.

Un evenement peut **reprendre un message cle du reporting** (bouton « Reprendre du
reporting » de l'etape evenements, present quand la plateforme a des squads concernees) : la liste montre les messages cles saisis cette
annee par les **squads concernees** de la plateforme, du plus recent au plus ancien, filtrables par
type (succes, alerte, risque), un meme texte d'une squad une seule fois
(`GET /api/steerco/platform/{id}/messages?period=`). Chaque message coche devient une
ligne : date du message, type en etiquette, gravite deduite (succes vert, alerte
orange, risque rouge). Un message deja present dans la liste est marque « Deja repris ».

Le one-pager **n'est pas stocke** : il est reconstruit a la demande a partir des
instantanes de l'**annee** du rapport. C'est ce qui garantit la coherence :

| Element du one-pager | Origine |
|---|---|
| Cartes KPI (valeur) | l'instantane du mois demande |
| Variation vs M-1 (fleche + delta) | calculee entre le mois et M-1 (janvier se compare a decembre de l'annee precedente) |
| Ligne SLA "mois en cours" | l'instantane du mois demande |
| Ligne SLA "moyenne annuelle" | moyenne des mois renseignes de l'annee |
| Couleur d'une cellule SLA | calculee de la valeur : au-dessus de 90 % vert, de 80 a 90 % orange, en dessous de 80 % rouge |
| Graphes KPI et incidents | serie de janvier a decembre de l'annee, en valeurs brutes (les memes chiffres que les cartes KPI) |
| Evenements (derniers / prochains) | l'instantane du mois demande ; la gravite colore la pastille de type |

> **Fenetre = annee civile.** Partout (graphes, grille de rattrapage, colonnes de
> l'assistant, colonnes du fichier Excel) la fenetre est la meme : les 12 mois de
> l'annee du rapport, de **janvier a decembre**. Les graphiques commencent donc
> toujours en janvier, et les mois qu'on saisit sont exactement ceux qu'on voit
> tracer. La definition unique est `year_months()` dans
> `backend/app/routers/steerco.py`.

> **Deux echelles quand les ordres de grandeur s'y opposent.** Une Software Factory
> qui compte ses builds par milliers et un DBaaS qui compte ses instances par dizaines
> ne se lisent pas sur la meme graduation : la petite courbe se couche sur l'axe. Le
> graphe KPI trie donc ses series par valeur maximale, les coupe au plus grand ecart
> d'ordre de grandeur, et **si cet ecart atteint un facteur 5** le groupe du haut passe
> sur une **seconde echelle, a droite**. La legende dit quelle courbe se lit de
> quel cote, en HTML comme en PPTX. Sur la page, elle se range en **deux groupes
> nommes** (« axe gauche », « axe droit ») : la mention se lit une fois par
> echelle et non une fois par courbe, ce qui lui epargne une ligne prise sur la
> hauteur du graphe. Sur la diapositive, la legende est celle de PowerPoint, ou
> l'on ne range rien : la mention y suit le nom de chaque serie concernee, comme
> le fait Excel.
>
> **Les couleurs des courbes sont choisies par calcul**, pas a l'oeil. Deux des
> six tenaient du meme bleu marine (un ecart de 5,5 sur 100) : deux courbes de la
> meme plateforme etaient litteralement de la meme couleur. Les six actuelles
> tiennent 25,9 entre voisines, 17,7 une fois simulee une protanopie ou une
> deuteranopie, et 13,8 entre les deux plus proches quelles qu'elles soient ;
> toutes passent 3 pour 1 de contraste sur le blanc, qu'un gris-bleu pale et un
> ambre clair ne passaient pas. Elles restent aussi a distance du vert, de
> l'ambre et du rouge, qui sur cette page disent la sante d'un SLA et les
> incidents : une courbe ne doit pas avoir l'air de le dire aussi.
> `backend/tests/test_steerco_palette.py` mesure ces ecarts plutot que de faire
> confiance a une relecture. Rien a configurer : la coupe se deduit
> des chiffres du mois, et en dessous du facteur 5 le graphe garde un seul axe, un
> second n'apportant qu'une colonne de nombres a lire. Voir `_split_axes()` et
> `SECONDARY_AXIS_RATIO` dans `backend/app/routers/steerco.py`.

## 4. Saisir : la liste du mois, le tableau de l'annee, l'assistant

Dans **Steerco > Reporting du mois**, l'etape 1 liste les plateformes du mois. La bascule
**Toute l'annee** montre **une ligne par plateforme, une case par mois** de l'annee
(`GET /api/steerco/board?year=&tribe_id=`). Chaque case dit ou en est le mois :

| Case | Etat |
|---|---|
| vide, en pointilles | rien de saisi |
| `2/5` orange | en cours : lignes remplies sur le total (KPI + SLA + incidents) |
| `✓` bleu | complet, pas encore valide |
| cadenas vert | **valide** |

Le bouton d'une plateforme, comme un clic sur une case, ouvre l'**assistant en 5
etapes** sur ce mois : le mois, les KPI, SLA et incidents, les evenements, puis un recapitulatif avec
**apercu en direct du one-pager** (rien n'est enregistre avant de cliquer sur
Enregistrer). Les tableaux affichent les 12 mois de l'annee en lecture seule a cote de
la colonne du mois, surlignee.

- **Reprendre le mois precedent** (etape du mois) copie les valeurs de M-1 (decembre de
  l'annee precedente pour un janvier) dans les **cases vides** : KPI, sous-metriques,
  SLA, incidents. Les evenements ne sont pas copies, ils sont ceux du mois.
- **Enregistrer** garde le mois en brouillon ; **Enregistrer et valider** le fige.
- La periode se choisit dans un **calendrier de mois** (l'annee en haut, les douze mois
  dessous, « Ce mois-ci » pour revenir).
- A la premiere utilisation, le repli **Importer l'historique de l'annee** ouvre une
  grille qui accepte un **coller depuis Excel** (une ligne par mois, de janvier a
  decembre). Les mois valides y sont figes, et le serveur les saute
  (`PUT /api/steerco/platform/{id}/history` renvoie `skipped`).

### Deux Steerco leaders sur le meme mois

Chaque mois porte une **version**. L'assistant renvoie celle qu'il a chargee
(`PUT /api/steerco/platform/{id}?period=` avec `{"data": ..., "version": n}`) ; si un
autre Steerco leader a enregistre entre-temps, la reponse est `409` (« Ce mois a ete
modifie entre-temps par X : rechargez avant d'enregistrer ») et rien n'est ecrase.
L'assistant propose **Recharger**.

## 5. Valider, rouvrir

Un mois vit en deux etats, `draft` (brouillon) puis `validated` :

| Action | Route | Effet |
|---|---|---|
| Valider un mois | `POST /api/steerco/platform/{id}/validate?period=` | lecture seule ; `400` si le mois est vide, `409` s'il l'est deja |
| Tout valider | `POST /api/steerco/validate?period=&tribe_id=` | valide chaque plateforme de la presentation, laisse les vides de cote et les nomme |
| Rouvrir | `POST /api/steerco/platform/{id}/reopen?period=` avec `{"reason": "..."}` | retour en brouillon ; motif obligatoire, audite |

Un mois valide refuse toute ecriture (`409`), en ligne comme par l'import. Un mois
**rouvert** garde sa date de revision (`revised_at`) : le one-pager et la diapositive
de ce mois affichent alors « Revise le JJ/MM/AAAA ». Chaque validation, reouverture et
designation est dans le journal d'audit (`steerco.validate`, `steerco.reopen`,
`steerco.leader.add`, `steerco.leader.remove`).

A la migration vers 4.0, **tous les mois existants sont en brouillon** : rien n'a ete
valide avant que le cycle existe.

## 6. Apercu et export

Dans **Reporting du mois**, **Apercu** deplie la diapositive d'une plateforme telle qu'elle sera
exportee, avec **Telecharger en PPTX**. Le menu d'export de la page propose le **HTML**
et le **PPTX** de la presentation (une diapositive 16:9 par plateforme) de la tribe affichee, ou de
la seule plateforme ouverte. Les documents sont rendus dans la langue de l'interface
(anglais par defaut).

La **mise en page** de la diapositive se regle dans le **Studio des exports**, seul
moteur de mise en page : dans Parametrage > Les plateformes, **Mettre en page dans le
Studio** ouvre le Studio sur la plateforme (`/exports?scope=platform:<id>`). Un Steerco
leader y concoit le perimetre `platform` des plateformes qu'il mene, **meme sans la
capacite `exports`** ; il ne voit pas les autres perimetres.

### Le rendu du graphique KPI, un reglage de la plateforme

Une plateforme peut suivre 10, 15 KPI ou plus. Une seule courbe par KPI sur un meme
graphique, parfois sur deux echelles, ne se lit plus au-dela de cinq. Dans la fiche
d'une plateforme (Parametrage > Les plateformes > Modifier), **Rendu du graphique KPI**
propose :

| Rendu | Ce qu'il dessine | Quand |
|---|---|---|
| Automatique (defaut) | Courbes jusqu'a 5 KPI, un petit graphique par KPI au-dela | Le bon choix sans y penser |
| Courbes | Toutes les courbes sur un graphique, second axe si les ordres de grandeur different | Peu de KPI comparables |
| Un petit graphique par KPI | Une case par KPI : son nom, sa derniere valeur, sa courbe sur sa propre echelle | Beaucoup de KPI |
| Tableau mois par mois | Les valeurs de chaque mois ; au-dela de 13 KPI, deux tableaux cote a cote sur les 4 derniers mois | Quand le chiffre compte plus que la tendance |

On peut aussi **choisir les KPI du graphique** (tous par defaut). Une courbe garde sa
couleur quelle que soit la selection. Le choix vaut pour tous les exports ; il est
stocke dans le gabarit de la plateforme (`template.display` : `kpi_chart`,
`chart_kpis`), via `PUT /api/steerco/platforms/{id}/display`, et modifier les lignes de
la plateforme ne l'efface pas. L'apercu et l'export acceptent aussi un rendu essaye,
non enregistre : `chart` et `chart_kpis` (repete) sur `onepager.html` et
`document.pptx?platform_id=`.

**Les cartes KPI** s'adaptent aussi, et **tous les KPI y figurent** (avant, la
diapositive gardait les 5 premiers et laissait tomber les autres) :

| KPI | Cadre KPI |
|---|---|
| 1 a 5 | La carte vedette et la rangee |
| 6 a 10 | Une grille de cartes compactes sur deux lignes |
| 11 a 24 | Une liste « nom, valeur, evolution » sur deux colonnes |
| 25 et plus | Une liste sur trois colonnes : nombres compacts (1,49 M), fleche coloree devant la valeur |

Rien ne peut deborder d'un cadre : les noms sont coupes a la largeur (avec « … »),
les grands nombres s'ecrivent en compact dans les cases etroites (tableau, petits
graphiques), le tableau se decoupe en autant de blocs que les KPI l'exigent, et la
legende des courbes reduit sa police jusqu'a tenir dans 40 % du cadre. Verifie de 5 a
30 KPI dans les quatre rendus, et fixe par un test geometrique
(`test_steerco_display.py`).

## 7. Les mails

Les reglages sont par tribe (`app_settings['steerco_mail:tribe:<id>']`), dans
**Parametrage > Le rappel et les destinataires** (`GET/PUT /api/steerco/mail?tribe_id=`).

- **Rappel mensuel** (actif par defaut, le **5** du mois, reglable de 1 a 28) : les
  Steerco leaders de la tribe recoivent la liste des plateformes de la presentation dont le **mois
  precedent** n'est pas valide, avec ou elles en sont. **Rien n'est envoye** quand tout
  est valide. Le planificateur horaire l'envoie une fois par mois
  (`last_reminder`), et retente a l'heure suivante si le serveur de mails ne repond
  pas (`app/steercomail.py:send_due_reminders`).
- **Envoi de la presentation** : a la main seulement, etape 3 de **Reporting du mois**
  (`POST /api/steerco/send?period=&tribe_id=`). Le mail resume chaque plateforme
  (chiffres cles, SLA sous le seuil) et joint le PPTX. Il est **refuse (`409`) tant
  qu'une plateforme de la presentation n'est pas validee** : ce qui part au comite est ce qui a ete
  valide. `400` sans destinataire, `502` si aucun mail n'a pu partir. Audite
  (`steerco.send`). Rien ne part automatiquement.

## 8. Import Excel

Alternative a la saisie en ligne, pour collecter les donnees hors application :
**Steerco > Reporting du mois, etape 1 > Importer un classeur Excel**.

1. **Choisir la plateforme**, puis **telecharger son fichier**. Le classeur est genere
   **pour cette plateforme** : nom pre-rempli, mois courant, et surtout **les lignes KPI
   et SLA de son gabarit**, donc exactement ce qui sera rendu. Sans plateforme choisie,
   on obtient la structure standard.
2. Remplir, puis **deposer** le fichier. Un resume s'affiche (plateforme, mois, nombre
   de mois / KPI / services SLA / evenements, mois valides laisses tels quels).

Le classeur a 7 onglets : Instructions, Infos, KPIs, SLA, Incidents,
Evenements passes, Evenements a venir.

- **Infos** : nom **exact** de la plateforme dans l'application (pre-rempli), mois du
  rapport (`AAAA-MM`), et les 3 sous-metriques Software Factory du mois en cours. Les
  fichiers anterieurs, dont la ligne s'appelait "Squad", restent acceptes.
- **KPIs / SLA / Incidents** : 12 colonnes = les mois de l'annee, de janvier a
  decembre. Le mois du rapport est marque d'une `*`.
- **Evenements** : Date, Type, Libelle, Gravite (Critique / Attention / OK / Prevu).

Rien a saisir pour les variations ni les couleurs : elles sont recalculees au rendu.
Les valeurs SLA sont des pourcentages plafonnes a 100 (le fichier le controle, et
l'import le replafonne).

### Regle de fusion : l'import ajoute et met a jour, il ne supprime jamais

C'est la garantie qui rend le fichier et la saisie en ligne coherents. Le classeur
n'a pas besoin d'etre la photo complete du mois :

| Dans le fichier | Effet |
|---|---|
| Une ligne KPI / SLA connue, avec une valeur | la valeur du mois est mise a jour |
| Une ligne KPI / SLA connue, **case vide** | la valeur deja saisie dans l'app est **conservee** |
| Une **ligne ajoutee a la main** avec une valeur | le KPI / service est **ajoute** a l'instantane |
| Un KPI / service **absent du fichier** | **conserve**, et signale dans le resume d'import |
| Onglet evenements **vide** | les evenements saisis dans l'app sont **conserves** |

L'import est ouvert aux **Steerco leaders**, sur les plateformes des tribes qu'ils
menent. Un **mois valide n'est pas modifie** : l'import le laisse tel que le comite l'a
vu et le cite dans son resume (`skipped_validated`). Rouvrez le mois avant de
reimporter s'il faut vraiment le corriger.

L'import est **idempotent** par `(plateforme, mois)` : reimporter n'introduit pas de
doublon. Il echoue en `400` si la plateforme est introuvable, si plusieurs plateformes
portent ce nom, ou si le mois du rapport n'est pas au format `AAAA-MM`.

> Les colonnes sont l'annee civile : changer le mois du rapport dans la meme annee
> ne decale pas les colonnes, cela deplace seulement l'asterisque du mois en cours.

### API directe (curl / CI)

```bash
# 1) recuperer le modele (mois courant ; ?platform_id= pour le fichier d'une plateforme)
curl -sk -b cookies.txt "https://<host>/api/steerco/import/template?platform_id=3" -o steerco.xlsx

# 2) importer le fichier rempli
curl -sk -b cookies.txt -F "file=@steerco.xlsx" https://<host>/api/steerco/import
```

Les anciennes routes `/api/admin/import-steerco` ont disparu en 4.0.

## 9. Plateformes et modele de la tribe

**Steerco > Parametrage**, sections 2 et 3, sur la tribe affichee :

1. **le modele de la tribe** : le squelette impose (KPI, sous-indicateurs, services
   SLA). Stocke dans `app_settings['steerco_model:tribe:<id>']`
   (`platforms.get_tribe_model`) ;
2. **les plateformes** : une plateforme, une diapositive. Une nouvelle plateforme part
   du modele ; sa fiche regle ensuite ses lignes, ses squads concernees (facultatives)
   et le rendu de son graphique, et **Appliquer le modele de la tribe** la ramene au
   modele en gardant les chiffres des elements qui restent. L'etat **Dans la presentation /
   Hors presentation** se bascule depuis la liste.

Les chiffres suivent leur libelle quand le squelette change (`platforms.remap_data`) :
retirer ou reordonner un element ne decale pas les valeurs des autres.

## 10. Droits, en resume

| Action | Qui |
|---|---|
| Plateformes, modele, saisie, historique, import, validation, reouverture, rappel, envoi | Steerco leaders de la tribe (tribe leader par defaut, designes, administrateur) |
| Designer ou retirer un Steerco leader | administrateur, tribe leader de la tribe |
| Retirer au tribe leader sa designation par defaut | administrateur |
| Lire la consolidation et les documents (`/entries`, `onepager.html`, `document.*`) | Steerco leaders, et personas ayant la capacite `steerco` (leur tribe) |
| Mettre en page la diapositive d'une plateforme dans le Studio | Steerco leaders de sa tribe, et qui a la capacite `exports` sur ce perimetre |

Toute ecriture est **auditee** (`platform.create`, `platform.update`,
`platform.delete`, `steerco.upsert`, `steerco.history`, `steerco.import`,
`steerco.validate`, `steerco.reopen`, `steerco.leader.add`, `steerco.leader.remove`,
`steerco.mail`, `steerco.send`).

## 11. Ou est le code

| Role | Fichier |
|---|---|
| API (plateformes, leaders, tableau, instantanes, validation, mails), agregation annuelle, rendu HTML et PPTX | `backend/app/routers/steerco.py` |
| Qui mene, qui lit, qui designe | `backend/app/steercoaccess.py` |
| Rappel mensuel et mail de la presentation | `backend/app/steercomail.py` |
| Gabarit, fusion des valeurs a l'enregistrement | `backend/app/platforms.py` |
| Modele et gabarit Excel, parsing, import | `backend/app/steerco_import.py` |
| Leaders, cycle de vie des mois, retrait des proprietaires | `backend/alembic/versions/0049_steerco_topic.py` |
| Decisions | [ADR 0018](adr/0018-steerco-is-a-topic-of-its-own.md) (et [ADR 0014](adr/0014-platform-is-the-steerco-reporting-unit.md) pour la plateforme comme unite) |
| Types et calculs partages (front) | `frontend/src/steerco.ts` |
| Page et onglets | `frontend/src/pages/SteercoPage.tsx`, `frontend/src/components/steerco/` |
| Reporting du mois, Parametrage, vue annuelle, import | `frontend/src/components/steerco/Steerco{Month,Settings,Board,Import}.tsx` |
| Assistant de saisie / grille de rattrapage | `frontend/src/components/Steerco{Wizard,Editor}.tsx` |
| Tests | `backend/tests/test_steerco*.py` |
| Maquette d'origine du one-pager (reference visuelle, non maintenue) | `docs/assets/kpi-onepager.reference.html` |
