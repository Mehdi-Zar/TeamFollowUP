# 34 - Annuaire d'entreprise et provisioning SCIM

> Public : administrateurs. Ce document décrit comment brancher l'application sur
> l'annuaire de l'entreprise, pour **chercher une personne** au moment de l'ajouter,
> et comment laisser le fournisseur d'identité **créer et désactiver les comptes**
> lui-même (SCIM 2.0).

## 1. Ce que l'annuaire apporte

Sans annuaire, on ajoute un membre d'équipe ou un compte en tapant son email et son
nom. Avec un annuaire configuré, un champ **« Rechercher dans l'annuaire »** apparaît :

| Écran | Ce que le choix remplit |
|---|---|
| Mes squads > Équipe (ajout d'un membre) | email, prénom, nom, et la fonction si le rôle est vide |
| Administration > Utilisateurs > Nouvel utilisateur | nom affiché, email |

La recherche part dès deux caractères, après une courte pause de frappe. Chaque
personne trouvée indique sa fonction, son service, et « a un compte » quand un
compte existe déjà pour son email. Sans annuaire configuré, rien ne change à l'écran.

## 2. Les sources prises en charge

Plusieurs sources peuvent être actives en même temps. Elles sont interrogées en
parallèle (6 s par source, 8 s au total) et leurs réponses sont **fusionnées par
email** : la première source qui nomme une personne l'emporte, les autres complètent
les champs vides (une fonction lue dans l'AD complète une fiche Entra). Une source qui
échoue n'empêche pas les autres de répondre : l'écran dit laquelle n'a pas répondu.

Toutes les connexions vérifient le certificat du serveur avec les autorités de
**Administration > Autorités de certification** (un annuaire émis par une autorité
interne s'y importe). Aucun réglage ne désactive cette vérification.

### Microsoft Entra ID (Microsoft Graph)

1. Dans Entra ID : *Inscriptions d'applications > Nouvelle inscription*.
2. *Autorisations d'API > Microsoft Graph > Autorisations d'application* :
   `User.Read.All`, puis *Accorder le consentement administrateur*.
3. *Certificats et secrets* : créer un secret client.
4. Dans l'application : **Administration > Annuaire > Microsoft Entra ID**, saisir
   l'ID du tenant, l'ID client et le secret, activer, **Tester**.

La recherche porte sur `displayName`, `mail` et `userPrincipalName`, comptes actifs
seulement (`$search` avec `ConsistencyLevel: eventual`). Les hôtes Graph et
d'authentification se changent pour les clouds nationaux (US Gov, Chine).

### LDAP / Active Directory

Active Directory, OpenLDAP, FreeIPA, tout annuaire LDAP v3.

| Champ | Exemple |
|---|---|
| URL | `ldaps://ad.corp.example:636` (ou `ldap://...:389` avec StartTLS) |
| Compte de service | `CN=svc-teamfollowup,OU=Services,DC=corp,DC=example` |
| Base DN | `DC=corp,DC=example` |
| Filtre des utilisateurs | `(&(objectClass=user)(mail=*)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))` pour les comptes AD actifs |
| Attributs où chercher | `displayName,cn,mail,givenName,sn,sAMAccountName` |

La correspondance des attributs (nom, email, prénom, nom, fonction, service) se règle
pour les annuaires qui n'utilisent pas les noms usuels. Le texte tapé est échappé
avant d'entrer dans le filtre LDAP. Le mot de passe du compte de service n'est jamais
envoyé sur une connexion en clair : sans LDAPS ni StartTLS, la recherche est refusée.

### Google Workspace

1. Dans Google Cloud : créer un compte de service et une clé JSON.
2. Dans la console d'administration Workspace : *Sécurité > Contrôle des accès et des
   données > Commandes des API > Délégation au niveau du domaine*, ajouter l'ID client
   du compte de service avec le scope
   `https://www.googleapis.com/auth/admin.directory.user.readonly`.
3. Dans l'application : coller la clé JSON, indiquer l'email d'un administrateur
   Workspace à emprunter, activer, **Tester**.

Les comptes suspendus ou archivés ne sont pas proposés.

## 3. Provisioning SCIM 2.0

Avec SCIM, c'est le fournisseur d'identité qui tient les comptes à jour : il crée le
compte quand on assigne l'application à quelqu'un, le met à jour quand l'annuaire
change, et le **désactive** quand la personne part ou n'est plus assignée. Ses
sessions ouvertes se terminent aussitôt.

### Mise en place

1. **Administration > Annuaire > Provisioning SCIM 2.0** : activer, choisir le
   persona et la tribe des comptes créés, **Générer le jeton**. Le jeton ne s'affiche
   qu'une fois ; seule son empreinte est conservée. En générer un nouveau révoque
   l'ancien.
2. Donner au fournisseur d'identité l'**URL du serveur SCIM** affichée
   (`https://<application>/scim/v2`) et le jeton.

**Entra ID** : *Applications d'entreprise > Nouvelle application > Créer votre propre
application* (hors galerie), puis *Provisionnement > Automatique* : URL du locataire =
l'URL SCIM, jeton secret = le jeton. Les correspondances par défaut conviennent
(`userPrincipalName` vers `userName`, `objectId` vers `externalId`).

**Okta** : application *SCIM 2.0 Test App (Header Auth)* ou intégration SCIM d'une
application maison, *Base URL* = l'URL SCIM, *Authorization* = `Bearer <jeton>`,
identifiant unique = `email`. Activer *Create Users*, *Update User Attributes* et
*Deactivate Users*.

OneLogin, JumpCloud, Ping et les autres connecteurs SCIM 2.0 se règlent de la même
façon.

### Ce que SCIM fait et ne fait pas

| Opération | Effet dans l'application |
|---|---|
| Créer (`POST /Users`) | Compte actif avec le persona et la tribe choisis ; les membres d'équipe déjà saisis avec cet email lui sont rattachés |
| Chercher (`GET /Users?filter=...`) | `userName`, `externalId`, `emails.value`, `id` avec `eq` |
| Mettre à jour (`PUT`, `PATCH`) | Nom, email, `externalId`, actif ou non |
| `active: false` | Compte désactivé, sessions terminées |
| Supprimer (`DELETE /Users`) | Compte **désactivé**, pas effacé : son historique reste |
| Groupes | Les tribes, en lecture seule ; les écritures sont refusées |

SCIM **ne change jamais le persona** d'un compte et ne peut pas créer
d'administrateur : un jeton volé ne donne pas l'administration. Le compte de secours
(break-glass) lui est invisible. Le persona et la tribe se règlent ensuite dans
**Administration > Utilisateurs**, comme pour tout compte.

Toutes les opérations SCIM sont tracées dans le journal d'audit (`scim.user_create`,
`scim.user_update`, `scim.user_status`, `scim.user_delete`).

## 4. Référence technique

| Élément | Où |
|---|---|
| Configuration (une entrée `app_settings['directory']`) | `backend/app/directoryconfig.py` |
| Connecteurs Entra / LDAP / Google | `backend/app/directory.py` |
| Recherche et écran d'administration | `backend/app/routers/directory.py` (`/api/directory/*`, `/api/admin/directory-config`) |
| Serveur SCIM | `backend/app/routers/scim.py` (`/scim/v2`) |
| Identifiant SCIM du compte | colonne `users.scim_external_id` (migration `0042`) |
| Composant de recherche | `frontend/src/components/DirectorySearch.tsx` |
| Écran d'administration | `frontend/src/pages/admin/directory.tsx` |
| Tests | `backend/tests/test_directory.py`, `backend/tests/test_scim.py`, `frontend/src/components/DirectorySearch.test.tsx` |
