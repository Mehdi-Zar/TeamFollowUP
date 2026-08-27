# 18 - Tests de bout en bout (Playwright)

Cette suite pilote l'application **réelle** dans un navigateur : l'image Docker,
servant le SPA construit et son API, devant un vrai PostgreSQL. Elle répond à la
seule question que ni les tests backend ni les tests unitaires du frontend ne
peuvent poser : *une fois tout assemblé et déployé, est-ce que ça marche ?*

Comme la [16](16-banc-kubernetes-sso.md) et la [17](17-observabilite.md), ce
document est écrit pour être suivi sans rien deviner.

---

## 1. Pourquoi contre l'application réelle

On aurait pu lancer Playwright contre `vite dev` avec une API simulée. C'est plus
rapide, plus stable, et ça ne prouve presque rien. Les bugs qui justifient une
suite E2E sont précisément ceux qui n'existent qu'une fois les morceaux assemblés :

- un **garde de route** qui laisse un membre ouvrir l'écran d'administration : le
  backend renvoie bien 403, mais l'utilisateur a vu un écran qu'il n'aurait pas dû
  voir, et les tests backend ne le sauront jamais ;
- un **build qui embarque un vieux chunk**, parce que `backend/app/static` a été
  copié depuis un build local périmé ;
- un **cookie de session** que le navigateur refuse d'envoyer, parce que
  `COOKIE_SECURE=true` sur une origine en HTTP simple ;
- une **montée de version** de React ou du bundler qui passe le typecheck et le
  build, et casse à l'exécution.

Le dernier point n'est pas théorique : cette suite a été écrite juste après le
passage à React 19 et Vite 8, et c'est elle qui a confirmé que l'application
fonctionnait vraiment, pas seulement qu'elle compilait.

---

## 2. Prérequis

Deux choses, toutes deux déjà décrites ailleurs si vous ne les avez pas :

| Outil | Pourquoi | Installation |
|---|---|---|
| **Docker** | faire tourner l'application et sa base | [doc 16, §2.1](16-banc-kubernetes-sso.md) |
| **Node.js 20+** | lancer Playwright | `winget install -e --id OpenJS.NodeJS.LTS` (Windows), `brew install node` (macOS), `sudo apt install nodejs npm` (Linux) |

Contrôle : `docker info --format "{{.ServerVersion}}"` et `node --version`.

Playwright télécharge son propre navigateur (environ 115 Mo la première fois), vous
n'avez pas besoin d'installer Chrome.

---

## 3. Lancer la suite

### 3.1 Démarrer l'application

Depuis la racine du dépôt :

```bash
docker compose up -d --build
```

- `up -d` : démarre en arrière-plan.
- `--build` : reconstruit l'image. **Nécessaire dès que vous avez touché au code**,
  sinon vous testez la version précédente, ce qui est la façon la plus efficace de
  perdre une heure.

Attendez que l'application réponde :

```bash
curl -s http://localhost:8000/api/health
# {"status":"ok","app":"TeamFollowUP"}
```

Le premier démarrage prend une minute : la base s'initialise, les migrations
Alembic s'appliquent, le compte de secours est créé.

### 3.2 Installer Playwright, une fois

```bash
cd e2e
npm install
npx playwright install chromium
```

`npm install` installe `@playwright/test` ; `playwright install chromium`
télécharge le navigateur. Les deux sont locaux à ce dossier : **rien de tout cela
n'entre dans l'application**. C'est la raison pour laquelle la suite vit dans
`e2e/` et non dans `frontend/` : le `Dockerfile` lance `npm install` sur
`frontend/package.json`, et Playwright y aurait fait télécharger un navigateur à
chaque construction d'image.

### 3.3 Lancer

```bash
npm test                # la suite, sans interface
npm run test:headed     # avec le navigateur visible, pour regarder ce qui se passe
npm run report          # le rapport HTML du dernier run
```

Sortie attendue :

```
Running 12 tests using 1 worker

  ok  1 [chromium] › tests\admin-org.spec.ts:21:7 › a tribe can be created, listed and deleted (2.4s)
  ...
  12 passed (20.2s)
```

### 3.4 Quand un test échoue

Playwright garde une **trace** de l'échec, c'est-à-dire l'enregistrement complet de
ce que le navigateur a fait : chaque action, chaque requête réseau, et une capture
à chaque étape.

```bash
npx playwright show-trace test-results/<nom-du-test>/trace.zip
```

Il écrit aussi un `error-context.md` à côté, qui contient **l'arbre
d'accessibilité de la page au moment de l'échec**. C'est souvent plus rapide que
la trace : on y voit tout de suite si le bouton attendu était absent, désactivé,
ou recouvert par autre chose.

---

## 4. Ce que couvre la suite

| Fichier | Parcours vérifiés |
|---|---|
| `tests/login.spec.ts` | l'écran de connexion est servi et ses champs sont atteignables par leur libellé ; de mauvais identifiants sont refusés **sans dire lequel des deux est faux** (pas d'énumération de comptes) ; le compte de secours entre ; la déconnexion invalide vraiment la session côté serveur ; une URL interne tapée par un visiteur non connecté ramène à la connexion |
| `tests/admin-org.spec.ts` | créer une tribu, la voir apparaître dans l'écran, la supprimer ; le journal d'audit enregistre l'action, la retrouve par filtre et affiche **le nom** de l'auteur et non son identifiant ; un filtre qui ne correspond à rien le dit au lieu de tout montrer ; la pagination avance et recule sans répéter de ligne |
| `tests/admin-sections.spec.ts` | les **dix-huit sections** de l'administration : chacune s'affiche, sans bandeau d'erreur, sans panneau vide et sans erreur JavaScript en console. C'est le filet qui a rendu défendable le découpage d'`AdminPage.tsx` : vert avant, vert après |
| `tests/roles.spec.ts` | un membre ne se voit pas proposer l'administration, ne l'obtient pas en tapant l'URL, et l'API la lui refuse aussi ; l'administrateur voit bien les sections ; le tableau de bord s'affiche sans bandeau d'erreur |

---

## 5. Les règles à respecter en écrivant un test ici

Chacune vient d'une erreur commise en écrivant cette suite.

### La suite écrit dans la base

Elle crée et supprime de vraies lignes. **Lancez-la contre une instance jetable.**
Chaque objet créé porte un nom unique (`uniqueName()`), pour qu'un reste de run
raté se voie immédiatement.

### Un seul worker, volontairement

`workers: 1` dans la configuration. Tous les tests partagent une base ; des workers
parallèles se marcheraient dessus. Une suite E2E instable est une suite que plus
personne ne regarde, puis que quelqu'un finit par désactiver.

### L'application est en anglais

La langue vient du **serveur** (Administration > Réglages, `default_lang`, anglais
à l'installation), pas du navigateur. L'option `locale` de Playwright ne change que
le formatage des dates et des nombres. Les sélecteurs utilisent donc les libellés
anglais.

### Les liens profonds de l'administration utilisent `?section=`

`/admin?section=audit`. Le `?tab=` est le sélecteur Steerco du tableau de bord et
ne fait rien ici : on atterrit sur le premier onglet, et le test échoue sur un
élément « introuvable » qui existe pourtant, ailleurs.

### La fenêtre de bienvenue s'ouvre à chaque test

Elle est mémorisée dans `localStorage`, et chaque test Playwright part d'un profil
vierge : elle est donc là **à tous les coups**. Son voile avale les clics, ce qui
produit des échecs qui ressemblent à des boutons cassés alors que rien ne l'est.
`signIn()` la ferme, comme le ferait un vrai utilisateur à sa première visite.

### Attendez que l'écran ait appliqué votre action

Les filtres du journal d'audit sont temporisés de 250 ms pour ne pas déclencher une
requête par frappe. Lire le tableau juste après avoir changé le nombre de lignes par
page lit encore la réponse **précédente**. Attendez un signal que la nouvelle
réponse est arrivée, ici le compteur « Showing 25 of N », avant d'affirmer quoi que
ce soit. C'est le bug qui a coûté le plus de temps dans cette suite, et il était
dans le test, pas dans l'application.

### Préférez les sélecteurs accessibles

`getByRole`, `getByLabel`, `getByText`. Ils décrivent ce que l'utilisateur voit,
survivent à un changement de classe CSS, et ils échouent quand un contrôle perd son
libellé, ce qui est en soi un bug d'accessibilité qu'on veut voir.

---

## 6. En intégration continue

Le job **End-to-end (Playwright, real stack)** de `.github/workflows/ci.yml` fait
exactement ce que vous venez de faire à la main : il démarre la pile avec
`docker compose up -d --build`, attend `/api/health`, installe Playwright et lance
la suite.

Il ne copie **pas** de fichier `.env` : les trois valeurs dont la suite a besoin
(`BREAKGLASS_PASSWORD`, `SEED_DEMO=false`, `COOKIE_SECURE=false`) sont passées
explicitement, pour que le résultat ne dépende jamais des réglages locaux de
quelqu'un.

En cas d'échec, il publie les journaux de l'application et le rapport HTML de
Playwright en artefact, conservé sept jours.

`retries: 1` uniquement en CI : une seule reprise absorbe le bruit d'infrastructure
(un conteneur qui finissait de démarrer) sans cacher un vrai bug intermittent
derrière trois reprises vertes.

---

## 7. Ce que la suite ne couvre pas

- **Le SSO.** OIDC et SAML demandent un fournisseur d'identité ; c'est le banc
  Kubernetes de la [16](16-banc-kubernetes-sso.md) qui les couvre, avec Keycloak et
  18 vérifications.
- **Les exports PPTX.** Un fichier binaire téléchargé se vérifie mal dans un
  navigateur ; les tests backend contrôlent leur structure.
- **Le rendu visuel.** Aucune comparaison de captures : ces tests vérifient le
  comportement, pas les pixels.
- **Les autres navigateurs.** Un seul projet, Chromium. Ajouter Firefox et WebKit
  est une ligne dans `playwright.config.ts` le jour où le besoin se pose.
