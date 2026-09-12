# 22 - Ecran de connexion : ce qui s'affiche, dans quel ordre

**Administration > Authentification > Ecran de connexion**, reserve a
l'administrateur. Tout se regle a l'ecran.

## 1. Le probleme

Une organisation qui se connecte par son IdP mais dont la page affiche d'abord un
formulaire email et mot de passe apprend le mauvais geste a chaque nouvel arrivant.
La personne cherche un mot de passe que personne ne lui donnera, essaie, echoue,
puis ecrit a l'administrateur. Le formulaire n'etait pas faux, il etait au mauvais
endroit.

Les ecrans de connexion des suites d'entreprise ont tous converge vers la meme
forme, et ce n'est pas une mode : **une methode principale**, en bouton plein, avec
le logo du fournisseur ; les autres en secondaire ; et ce que personne ne doit
utiliser par defaut n'est pas affiche du tout, juste atteignable.

## 2. Ce qui se regle

| Reglage | Effet |
|---|---|
| Message d'accueil | La phrase sous le nom de l'application |
| Ordre | Monter / descendre chaque methode ; la page suit cet ordre |
| Affichee | Retire une methode de la page sans la desactiver dans la configuration |
| Principale | La methode rendue en bouton plein ; les autres sont secondaires |
| Libelle | Le texte du bouton, a la place du libelle par defaut |
| Phrase sous le bouton | Une ligne d'explication, par exemple « compte de l'entreprise » |
| Logo | Une image dans le bouton, pour OIDC et SAML |

Une methode **non configuree n'est jamais proposee**, quoi qu'on coche : un bouton
qui mene a une page d'erreur est pire que pas de bouton. Et l'ecran garde toujours
les trois methodes dans son tableau, y compris celles qui sont eteintes, sinon on
ne pourrait plus les rallumer.

Le logo est stocke en data URI dans la configuration : rien a gerer cote fichiers,
il suit les sauvegardes comme le reste du reglage, et il est plafonne a 200 ko
parce qu'un PNG de 4 Mo rendrait chaque lecture de la configuration aussi lourde
que lui.

## 3. Le formulaire email et mot de passe

Trois etats :

- **Affiche** : sous les boutons, comme avant. C'est le defaut, donc une
  installation existante ne change pas.
- **Replie derriere un lien** : la page montre d'abord le SSO, et « Autres options
  de connexion » ouvre le formulaire.
- **Reserve au lien secret** : le formulaire n'apparait pas, sauf si l'URL porte le
  jeton du lien de secours.

> **C'est de la lisibilite, pas du controle d'acces.** `POST /api/auth/login`
> continue de fonctionner dans les trois modes, protege par la limitation par IP.
> C'est volontaire : si masquer le formulaire empechait la connexion locale, une
> organisation en mode secret perdrait son **compte de secours** le jour ou l'IdP
> tombe, c'est a dire exactement le jour ou elle en a besoin. Ce que le mode
> supprime, c'est l'invitation.

## 4. Le lien de secours

En mode secret, l'application **genere** un jeton (un secret qu'on tape est un
secret qu'on reutilise) et affiche le lien complet, a copier et a garder hors de
l'application. « Renouveler » en fabrique un autre et invalide le precedent.

Le jeton ne sort **jamais** de la configuration publique : la page envoie ce qu'on
lui a donne (`GET /api/auth/config?k=...`) et le serveur repond seulement si le
formulaire s'ouvre. La comparaison est a temps constant, pour que l'endpoint ne
serve pas a deviner le jeton caractere par caractere. Un jeton faux ne dit rien de
plus qu'un mot de passe faux.

## 5. Ou est le code

| Role | Fichier |
|---|---|
| Reglages, normalisation, vue publique | `backend/app/authconfig.py` (`normalize_login_methods`, `login_screen`) |
| Endpoint public `GET /api/auth/config` | `backend/app/routers/auth.py` |
| Page de connexion | `frontend/src/pages/LoginPage.tsx` |
| Panneau d'administration | `frontend/src/pages/admin/authentication.tsx` (`LoginScreenPanel`) |
| Tests | `backend/tests/test_login_screen.py` |

Voir aussi [05](05-security.md) pour l'authentification elle-meme et le compte de
secours.
