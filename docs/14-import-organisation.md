# 14 - Import de l'organisation (tribu, squads, initiatives, OTD)

Peupler un environnement (local ou production S3NS) avec votre organisation reelle
a partir d'un **fichier Excel a remplir**, **sans reconstruire l'image**. Vous
deposez le fichier dans l'application qui tourne deja, elle l'importe directement.

## 1. Le principe

L'import se fait **par upload** vers l'application en marche (UI admin ou API).
Le fichier est lu **en memoire** et importe : aucun `docker build`, aucun
redeploiement. La meme methode marche a l'identique en local et en prod S3NS.

L'import est **idempotent** : relançable sans creer de doublons (met a jour
l'existant, matche par cle naturelle : nom de tribu, email, nom de squad, titre).

## 2. Depuis l'application (recommande)

**Administration -> Import** :

1. **Telecharger le modele** Excel (bouton dans la page).
2. Remplir les **4 onglets** puis enregistrer le fichier.
3. **Deposer** le fichier et cliquer **Importer**. Un resume s'affiche (tribu,
   nombre de squads / initiatives / OTD, elements crees).

Reservé aux administrateurs. Fonctionne pareil sur l'environnement de prod S3NS
(via le meme ecran, a travers la gateway).

## 3. Remplir le fichier Excel

Les 4 onglets, colonnes lues **par position** (l'ordre compte, pas le libelle) ;
les lignes vides sont ignorees :

- **Tribu** : Annee, Nom de la tribu, Description, Tribe leader (nom + email).
- **Squads** : Nom, Type (`product` | `transverse`), Squad leader (nom + email),
  Produits, Materiel, KPIs (oui/non), Budget (oui/non). Une ligne par squad.
- **Initiatives** : Titre, Squad concernee, Owner, Echeance (AAAA-MM-JJ), Description.
- **OTD** : Titre, Squad concernee (l'owner = son leader), Date d'engagement
  (AAAA-MM-JJ), Description.

Les leaders sont crees **actifs** et **compatibles SSO** (reconnus par email au
1er login IdP, ils heritent de ce compte/role). Le mot de passe local par defaut
est `changeme` (surcharge : `IMPORT_DEFAULT_PASSWORD`).

> Le format **YAML** est aussi accepte a l'upload (`.yaml`, voir
> `org.example.yaml`). Le lecteur reconnait `.xlsx` ou `.yaml`.

## 4. Alternative : API directe (curl / CI)

Memes deux operations, sans l'UI (utile pour un pipeline). Authentifie en admin.

```bash
# 1) recuperer le modele
curl -sk -b cookies.txt https://<host>/api/admin/import-org/template -o org.xlsx

# 2) importer le fichier rempli
curl -sk -b cookies.txt -F "file=@org.xlsx" https://<host>/api/admin/import-org
```

En local, `<host>` = `localhost:8443`. En prod S3NS, l'hote de votre gateway.

## 5. Alternative : CLI (hors ligne)

Un point d'entree CLI reste disponible pour un import sans passer par l'API
(le fichier doit etre accessible dans le conteneur) :

```bash
python -m app.import_org --template          # (re)generer data/org.template.xlsx
python -m app.import_org data/org.xlsx       # importer un fichier
```

## 6. Notes

- **Idempotent** : relancer apres modification du fichier met a jour l'existant
  (matche par nom / email / titre) et cree les nouveaux. Renommer = nouvel element.
- **Repartir de zero** avant un import : detruire les donnees puis reimporter.
  En local : `docker compose down -v && docker compose up -d --build` (base vide
  avec `SEED_DEMO=false`), puis importer. En prod, videz selon votre politique.
- `org.xlsx` peut contenir des noms/emails reels : il est **gitignore** (seuls
  `org.template.xlsx` et `org.example.yaml` sont suivis).
