# 15 - Steerco (comite de pilotage) : saisie mensuelle et one-pager

Le module **Steerco** produit, pour le comite de pilotage, un **one-pager KPI par
plateforme** (HTML / PPTX) construit automatiquement a partir d'instantanes mensuels.
Les contributeurs saisissent des **valeurs brutes** ; tout le reste (variation vs M-1,
couleurs SLA, graphiques de l'annee) est **calcule au rendu**, jamais tape a la main.

Module optionnel, **desactive par defaut** : Administration -> Modules -> `steerco`.

## 1. Une plateforme, une diapositive, n contributeurs

L'unite de reporting est la **plateforme**, pas la squad. Une plateforme peut etre
alimentee par plusieurs squads : Sovereign Platform l'est par Managed Services et Sovereign LZ,
tandis que Data Platform ou Vault Platform n'ont qu'une source. Le comite veut une diapositive par
plateforme dans les deux cas.

Ce qui rend cela possible sans fusion hasardeuse : la plateforme porte le **gabarit**
de sa diapositive (`platforms.template`), et **chaque element est attribue a une seule
squad contributrice**. Une carte KPI, une colonne SLA, le compteur d'incidents : un
element, un proprietaire. Deux squad leaders remplissent donc la meme diapositive sans
jamais s'ecraser, et aucun chiffre affiche n'est anonyme.

```json
{"kpis": [{"label": "K8aaS", "owner_squad_id": 9, "sub": ["GitLab"]}],
 "sla":  [{"label": "Gitlab", "owner_squad_id": 8}],
 "incidents": {"owner_squad_id": 8}}
```

L'instantane mensuel (table `steerco_entries`, unique sur `(platform_id, period)`,
`period` au format `AAAA-MM`) est **positionnel** par rapport au gabarit :
`data["kpis"][i]` porte la valeur de `template["kpis"][i]`.

```json
{"kpis": [{"label": "Cloud Users", "value": "247"}],
 "sla": {"services": ["Incidents", "Gitlab"], "cells": [{"v": "99,4%"}]},
 "incidents": "13",
 "last_events": [{"date": "12/07", "tag": "Incident", "text": "...", "sev": "amber", "squad_id": "8"}],
 "next_events": []}
```

A l'enregistrement, le serveur **reconstruit le squelette depuis le gabarit** et ne
reprend du payload que les valeurs des elements dont l'appelant est proprietaire
(`app/platforms.py:merge_owned`). Deux consequences utiles : un onglet reste ouvert ne
peut pas renommer une ligne de la diapositive, et une saisie concurrente ne peut pas
effacer la colonne du voisin.

Les **evenements** sont la seule section partagee : chacun ajoute les siens, chaque
ligne porte sa squad d'origine, et personne ne peut modifier celles des autres.

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

## 2. Declarer les plateformes (tribe leader / admin)

**Administration -> Plateformes**. Pour chaque plateforme :

1. son **nom** (celui qui titrera la diapositive) et, au besoin, une description ;
2. les **squads contributrices** (une squad peut en alimenter plusieurs) ;
3. le **contenu de la diapositive** : les cartes KPI (avec leurs sous-metriques), les
   colonnes SLA, le compteur d'incidents, et pour chacun **la squad qui le remplit**.

Le tableau signale en orange les elements **non attribues** : ils ne sont le travail de
personne, resteraient vides tous les mois, et seul le tribe leader peut les saisir tant
qu'ils le sont.

Retirer une squad des contributrices **libere** les elements qu'elle possedait (ils
repassent en non attribues) plutot que de les geler sur une squad absente.

`squads.steerco_enabled` est **derive** : une squad est "en Steerco" parce qu'elle
contribue a une plateforme **dont le steerco est actif**, pas parce que quelqu'un a
coche une case. Le drapeau sert uniquement a decider si l'etape Steerco existe dans la
Saisie, et c'est pour cela qu'il compte les plateformes actives et non toutes : il
repondait "oui" a une squad rattachee a une plateforme dont le steerco est coupe,
c'est a dire une squad qui n'a rien a saisir. L'etape s'ouvrait alors sur une liste
vide. Une etape ou l'on ne peut rien faire se traverse quand meme, et fait douter
d'avoir oublie quelque chose.

## 3. Saisir (contributeur)

**Saisie -> etape Steerco**, qui n'apparait que pour une squad qui alimente une
plateforme active. La carte liste **les plateformes que la squad alimente**,
rappelle la cadence (mensuelle, alors que le reporting au-dessus est hebdomadaire),
indique si le mois est deja rempli, quand, par qui, et **qui manque encore**.

Le bouton ouvre un **assistant en 5 etapes** : le mois, les KPI, SLA et incidents, les
evenements, puis un recapitulatif avec **apercu en direct du one-pager** (rien n'est
enregistre avant l'envoi). Les tableaux affichent les 12 mois de l'annee en lecture
seule, la colonne du mois en cours etant modifiable **pour les seules lignes dont on est
proprietaire** : les autres restent visibles, grisees, avec le nom de la squad qui les
doit. On voit donc toujours la diapositive entiere, y compris ce qui manque.

A la premiere utilisation, le repli **"Importer l'historique de l'annee"** ouvre une
grille qui accepte un **coller depuis Excel** (une ligne par mois, de janvier a
decembre) pour amorcer les graphes en une fois. Les colonnes des autres contributeurs y
sont desactivees, et le serveur applique de toute facon la meme regle de propriete.

## 4. Consulter et exporter (leadership)

**Dashboard -> onglet Steerco** (admins et tribe leaders) : choisir un mois et une
plateforme (ou toutes), l'apercu s'affiche dans la page. La liste nomme, plateforme par
plateforme, **les contributeurs en retard** : une diapositive n'est finie que quand son
dernier contributeur a rempli sa part. Le menu d'export de la page propose le **HTML**
et le **PPTX** (une diapositive 16:9 par plateforme). Les documents sont rendus dans la
langue de l'interface (anglais par defaut).

## 5. Import Excel (admin)

Alternative a la saisie en ligne, pour collecter les donnees hors application :
**Administration > Plateformes et Steerco > Importer des donnees Steerco**.

1. **Choisir la plateforme**, puis **telecharger son fichier**. Le classeur est genere
   **pour cette plateforme** : nom pre-rempli, mois courant, et surtout **les lignes KPI
   et SLA de son gabarit**, donc exactement ce qui sera rendu. Sans plateforme choisie,
   on obtient la structure standard.
2. Remplir, puis **deposer** le fichier. Un resume s'affiche (plateforme, mois, nombre
   de mois / KPI / services SLA / evenements).

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

Cette voie est **reservee a l'admin** et travaille en masse : elle fusionne par libelle
et ne passe pas par l'attribution element par element. Un contributeur qui remplit sa
part passe par l'application, ou la propriete est verifiee ligne a ligne.

L'import est **idempotent** par `(plateforme, mois)` : reimporter n'introduit pas de
doublon. Il echoue en `400` si la plateforme est introuvable, si plusieurs plateformes
portent ce nom, ou si le mois du rapport n'est pas au format `AAAA-MM`.

> Les colonnes sont l'annee civile : changer le mois du rapport dans la meme annee
> ne decale pas les colonnes, cela deplace seulement l'asterisque du mois en cours.

### API directe (curl / CI)

```bash
# 1) recuperer le modele (mois courant ; ?platform_id= pour le fichier d'une plateforme)
curl -sk -b cookies.txt "https://<host>/api/admin/import-steerco/template?platform_id=3" -o steerco.xlsx

# 2) importer le fichier rempli
curl -sk -b cookies.txt -F "file=@steerco.xlsx" https://<host>/api/admin/import-steerco
```

## 6. Droits

| Action | Qui |
|---|---|
| Declarer une plateforme, changer ses contributrices, attribuer les elements | admin, tribe leader (dans son perimetre) |
| Saisir les elements dont sa squad est proprietaire, rattraper l'historique, voir l'apercu | le leader, les co-leaders et les contributeurs des squads contributrices (writer + droit d'edition sur la squad) |
| Saisir un element non attribue | admin, tribe leader |
| Lire la consolidation et les documents (`/entries`, `onepager.html`, `document.*`) | admin, tribe leader (dans leur perimetre) |
| Telecharger le modele et importer un fichier | admin |

Un utilisateur qui ne contribue a aucune squad de la plateforme recoit `403` en
ecriture. Toute ecriture est **auditee** (`platform.create`, `platform.update`,
`platform.delete`, `steerco.upsert`, `steerco.history`, `steerco.import`).

## 6 bis. Un seul menu : Plateformes et Steerco

Tout ce qui organise le Steerco se regle a un seul endroit, Administration >
**Plateformes et Steerco**, tenu par le tribe leader (et l'admin), sur sa tribu :

1. **le modele de la tribu** : le squelette qu'il impose (KPI, sous-indicateurs,
   services SLA, sans proprietaire). Stocke dans
   `app_settings['steerco_model:tribe:<id>']` (`platforms.get_tribe_model`) ;
2. **les plateformes** : une plateforme, un Steerco. Une nouvelle plateforme part du
   modele ; son squelette s'ajuste ensuite plateforme par plateforme, et **Appliquer
   le modele de la tribu** l'y ramene en gardant les proprietaires et les chiffres des
   elements qui restent ;
3. **les squads concernees** et le proprietaire de chaque chiffre ;
4. **l'import Excel**, limite aux plateformes de la tribu.

« Mes squads » ne regle plus rien du Steerco : il renvoie vers ce menu. La saisie des
chiffres reste dans **Reporting**, par les squads concernees, et le resultat se lit
dans l'onglet **Steerco du tableau de bord**, ouvert a toute la tribu, ou un bouton
« Gerer les plateformes » mene au menu pour qui en a le droit.

Les chiffres suivent leur libelle quand le squelette change
(`platforms.remap_data`) : retirer ou reordonner un element decalait auparavant les
valeurs des autres a l'enregistrement suivant.

## 7. Ou est le code

| Role | Fichier |
|---|---|
| API (plateformes + instantanes), agregation annuelle, rendu HTML et PPTX | `backend/app/routers/steerco.py` |
| Gabarit, propriete par element, fusion a l'enregistrement | `backend/app/platforms.py` |
| Modele et gabarit Excel, parsing, import | `backend/app/steerco_import.py` |
| Tables `platforms`, `platform_contributors`, cle de `steerco_entries` | `backend/alembic/versions/0029_platforms.py` |
| Decision et alternatives ecartees | [ADR 0014](adr/0014-platform-is-the-steerco-reporting-unit.md) |
| Types et calculs partages (front) | `frontend/src/steerco.ts` |
| Declaration des plateformes (Administration) | `frontend/src/pages/admin/platforms.tsx` |
| Assistant de saisie / grille de rattrapage / onglet consolidation | `frontend/src/components/Steerco{Wizard,Editor,Consolidation}.tsx` |
| Tests | `backend/tests/test_steerco.py`, `backend/tests/test_steerco_model.py` |
| Maquette d'origine du one-pager (reference visuelle, non maintenue) | `docs/assets/kpi-onepager.reference.html` |
