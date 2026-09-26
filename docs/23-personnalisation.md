# 23 - Personnalisation de l'apparence

**Administration > Personnalisation**, reserve a l'administrateur. Couleurs,
logos, typographie, densite, et le pied de page des emails. Rien a reconstruire :
le theme de l'application etait deja pilote par des variables CSS, elles sont
desormais administrables.

## 1. Ce qui se regle

| Bloc | Contenu |
|---|---|
| Identite | Nom et sous-titre de l'application, logo, icone d'onglet, fond de l'ecran de connexion, logo des documents |
| Couleurs | Douze variables : principale, principale foncee, accent, deux teintes claires, vert, orange, rouge, texte, texte secondaire, bordures, fond. Cinq palettes pretes a l'emploi |
| Typographie et mise en page | Police (liste fermee), taille du texte de 85 a 125 %, arrondi des angles de 0 a 24 px, densite confortable ou compacte, ombres |
| Emails et documents | Pied de page ajoute aux emails envoyes |

L'apercu s'applique **en direct a la page reelle**, pas dans une vignette : une
palette se juge sur les vraies cartes, les vrais badges et le vrai contraste.
Quitter l'ecran sans enregistrer remet l'apparence publiee. **Reinitialiser**
revient au theme livre, ce qui est la seule sortie sure d'une combinaison devenue
illisible.

Le nom et le sous-titre restent stockes dans les reglages generaux, et le gabarit
PowerPoint dans Administration > Import : un nom d'application n'est pas une
couleur, et l'ecran se contente de les rassembler la ou on les cherche.

## 2. Pourquoi la validation est le sujet

Ce que cet ecran produit **part dans une feuille de style et dans des balises
d'image**. Une valeur libre y serait une injection : il suffirait de

```
--navy: red; } body { display:none } /*
```

pour rendre l'application invisible a tout le monde, et d'une URL distante pour
que chaque affichage de l'ecran de connexion, y compris avant authentification,
signale a un tiers qui l'ouvre et quand.

Chaque valeur est donc validee **par forme** cote serveur (`app/branding.py`) :

- une couleur est `#rgb` ou `#rrggbb`, sinon elle retombe sur la valeur livree ;
- une image est une `data:` URI d'image, donc embarquee ; une URL distante est
  refusee, pas tronquee ;
- une police est choisie dans une liste fermee, parce que le nom part tel quel
  dans `font-family` ;
- les nombres sont **bornes** plutot que refuses : un rayon de 400 pixels est une
  faute de frappe, pas une raison d'echouer ;
- les images sont plafonnees a 400 ko, parce que ce reglage est lu a chaque
  chargement de page, par tout le monde, avant authentification.

Le resultat est toujours complet : un champ absent ou refuse retombe sur le
defaut, donc la page n'a jamais a arbitrer entre « non defini » et « vide ».

Le pied de page des emails est **echappe** avant d'etre insere dans un email HTML :
il est saisi dans un champ libre et rendu dans du HTML.

## 3. Comment le theme arrive a la page

Le serveur publie des **variables CSS** dans `/api/config`, et la page les ecrit
sur l'element racine. Deux consequences utiles : le nom de chaque variable est
decide au meme endroit que sa validation, et un reglage retire revient tout seul a
la valeur de `theme.css`, sans feuille injectee a nettoyer.

L'apparence voyage avec la configuration publique plutot que dans un appel a part :
l'ecran de connexion en a besoin **avant** toute authentification, et un second
appel ferait clignoter le theme par defaut a chaque ouverture.

## 4. Ou est le code

| Role | Fichier |
|---|---|
| Defauts, validation, variables CSS | `backend/app/branding.py` |
| Publication dans `/api/config` | `backend/app/generalconfig.py` (`public_config`) |
| API `/api/admin/branding` | `backend/app/routers/admin.py` |
| Application du theme | `frontend/src/config.tsx` (`applyBranding`) |
| Ecran d'administration | `frontend/src/pages/admin/branding.tsx` |
| Pied de page des emails | `backend/app/smtpconfig.py`, `backend/app/mail.py` |
| Tests | `backend/tests/test_branding.py` |

Voir aussi [22](22-ecran-de-connexion.md) pour l'ecran de connexion lui-meme.
