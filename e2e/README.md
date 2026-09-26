# Tests de bout en bout (Playwright)

Ces tests pilotent **l'application réelle** dans un navigateur : l'image Docker,
qui sert le SPA construit et son API, devant un vrai PostgreSQL. Pas de `vite dev`,
pas d'API simulée, parce que les bugs qui valent la peine d'être attrapés ici sont
ceux qui n'existent qu'une fois les morceaux assemblés : un garde de route qui
laisse passer le mauvais rôle, un build qui embarque un vieux chunk, un cookie que
le navigateur refuse d'envoyer.

**Le mode d'emploi complet est [`docs/18-tests-e2e.md`](../docs/18-tests-e2e.md).**

## Lancer

Depuis la racine du dépôt, l'application doit tourner :

```bash
docker compose up -d --build
curl -s http://localhost:8000/api/health     # doit repondre {"status":"ok",...}
```

Puis, depuis ce dossier :

```bash
npm install
npx playwright install chromium
npm test                # la suite
npm run test:headed     # avec le navigateur visible, pour regarder
npm run report          # le rapport HTML du dernier run
```

## Ce que couvre la suite

| Fichier | Parcours |
|---|---|
| `tests/login.spec.ts` | l'écran de connexion, le refus des mauvais identifiants sans divulguer lequel est faux, la connexion du compte de secours, la déconnexion qui invalide vraiment la session, le garde de route sur une URL tapée à la main |
| `tests/admin-org.spec.ts` | créer une tribu, la voir dans l'écran, la supprimer ; le journal d'audit qui enregistre l'action et la retrouve par filtre ; la pagination qui ne répète pas de ligne |
| `tests/admin-sections.spec.ts` | les dix-huit sections de l'administration s'affichent chacune sans erreur ; c'est le filet de sécurité pour refactoriser cet écran |
| `tests/roles.spec.ts` | un membre ne se voit pas proposer l'administration, ne peut pas y accéder par l'URL, et l'API le refuse aussi ; l'administrateur, lui, voit les sections ; le tableau de bord s'affiche |

## Ce qu'il faut savoir avant d'écrire un test ici

- **La suite écrit dans la base.** Elle crée et supprime de vraies lignes. Lancez-la
  contre une instance jetable, jamais contre des données qui comptent.
- **Un seul worker, volontairement.** Tous les tests partagent la même base ; des
  workers parallèles se marcheraient dessus, et une suite E2E instable est une
  suite que plus personne ne regarde.
- **L'application est en anglais par défaut** (réglage serveur `default_lang`), pas
  dans la langue du navigateur. Les sélecteurs utilisent donc les libellés anglais.
- **Les liens profonds de l'administration utilisent `?section=`**, pas `?tab=`.
- **La fenêtre de bienvenue s'ouvre à chaque test** (elle est mémorisée dans
  `localStorage`, et chaque test part d'un profil vierge). `signIn()` la ferme ;
  son voile avale les clics et donne des échecs qui ressemblent à des boutons
  cassés alors que rien n'est cassé.
- **Attendez que l'écran ait appliqué votre action avant d'affirmer quoi que ce
  soit.** Les filtres du journal d'audit sont temporisés de 250 ms : lire le
  tableau juste après avoir changé un filtre lit encore l'ancienne réponse.
