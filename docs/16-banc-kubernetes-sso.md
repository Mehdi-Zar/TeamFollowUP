# 16 - Banc Kubernetes de bout en bout, avec Keycloak en OIDC et SAML

Rejouer sur votre poste le déploiement de TeamFollowUP dans un vrai cluster, derrière
une passerelle qui termine le TLS avec une autorité interne, puis valider les deux
protocoles de connexion contre un fournisseur d'identité réel.

Validé sur minikube (pilote Docker), Kubernetes v1.34, Keycloak 26.0, Envoy 1.31 :
**18 vérifications sur 18**.

Tous les fichiers cités vivent dans [`bench/k8s-sso/`](../bench/k8s-sso) et sont versionnés.
Seule la PKI est produite localement et reste hors du dépôt.

## Ce que vous obtenez

Un cluster à quatre pods : l'application servie en HTTP simple sur un port unique
(le modèle recommandé au [§6.9 du guide de déploiement](12-deployment-guide.md)), PostgreSQL,
Keycloak en fournisseur d'identité, et une passerelle Envoy qui termine le TLS. Deux noms
publics sur un seul certificat, émis par une autorité que vous créez. Puis un pilote de tests
qui joue une connexion OIDC complète et une connexion SAML complète, en vérifiant réellement
le certificat.

Comptez une vingtaine de minutes la première fois, l'essentiel étant le téléchargement des
images. Rien n'est écrit dans votre fichier `hosts` ni dans le magasin de certificats de
votre poste.

## Prérequis

| Outil | Rôle | Vérification |
|---|---|---|
| Docker | construire l'image, faire tourner le nœud minikube | `docker info` |
| minikube | le cluster Kubernetes | `minikube version` |
| kubectl | piloter le cluster | `kubectl version --client` |
| OpenSSL | créer l'autorité et le certificat | `openssl version` |
| Python 3 | lancer le pilote de tests | `python --version` |

Prévoyez environ 6 Go de mémoire disponible pour Docker : Keycloak et le cluster en
consomment l'essentiel.

## 1. Se placer dans le dossier du banc

```bash
cd bench/k8s-sso
```

## 2. Créer l'autorité de certification interne

Une autorité dédiée, puis un certificat serveur portant les deux noms publics. C'est le cas
réel d'un load balancer interne derrière un DNS privé.

```bash
./make-pki.sh          # doit se terminer par : pki/tls.crt: OK
```

Le script écrit `pki/ca.crt`, `pki/ca.key`, `pki/tls.crt` et `pki/tls.key`. Ce dossier est
gitignoré : il contient des clés privées.

> **Piège rencontré.** Sans les extensions `basicConstraints` et `keyUsage` sur l'autorité,
> OpenSSL 3.5 rejette la chaîne avec `CA cert does not include key usage extension`. C'est
> pour cela que l'autorité passe par un fichier de configuration plutôt que par `-subj` seul.

> **Sous Git Bash / Windows.** Le script exporte déjà `MSYS_NO_PATHCONV=1`. Si vous rejouez
> les commandes `openssl` à la main, préfixez-les de la même manière, sinon le `/CN=...` est
> réécrit en chemin Windows et le sujet du certificat devient inexploitable.

## 3. Les noms publics, sans toucher au fichier hosts

Le banc utilise `app.localtest.me` et `idp.localtest.me`. `localtest.me` est un domaine
public dont tous les sous-domaines résolvent vers `127.0.0.1`. Aucune modification de votre
poste n'est donc nécessaire.

```bash
ping -n 1 app.localtest.me      # Windows
ping -c 1 app.localtest.me      # Linux / macOS
```

Si votre DNS d'entreprise bloque ce domaine, remplacez partout par `app.127.0.0.1.nip.io` et
`idp.127.0.0.1.nip.io`, qui rendent le même service, et ajustez les noms alternatifs du
certificat dans `make-pki.sh` en conséquence.

## 4. Démarrer le cluster

```bash
minikube start --driver=docker --cpus=4 --memory=6144 --profile=tfu
kubectl config use-context tfu
kubectl get nodes
```

minikube peut signaler qu'il ne joint pas `registry.k8s.io` depuis l'intérieur du nœud. Sans
conséquence ici : toutes les images sont injectées depuis votre poste à l'étape suivante.

## 5. Construire et injecter les images

L'image applicative est construite depuis le dépôt, les trois autres sont récupérées sur
votre poste puis chargées dans le nœud.

```bash
docker build -t teamfollowup-app:bench ../..
docker pull postgres:16-alpine
docker pull envoyproxy/envoy:v1.31-latest
docker pull quay.io/keycloak/keycloak:26.0

for img in teamfollowup-app:bench postgres:16-alpine \
           envoyproxy/envoy:v1.31-latest quay.io/keycloak/keycloak:26.0; do
  minikube -p tfu image load "$img"
done
```

`20-app.yaml` référence le tag `teamfollowup-app:bench-v6`, celui de la dernière passe de
mise au point. Alignez le tag que vous construisez et celui du manifeste, et changez-en à
chaque reconstruction.

> **Piège rencontré, le plus coûteux.** `minikube image load` sur un tag **déjà présent** ne
> remplace pas l'image dans le cluster. Après une modification du code, un correctif peut
> sembler sans effet alors que le pod exécute encore l'ancien binaire. Utilisez un nouveau
> tag à chaque reconstruction (`:bench-v2`, `:bench-v3`...) et vérifiez ce qui tourne
> réellement :
>
> ```bash
> kubectl -n tfu exec deploy/teamfollowup-app -- grep -c motif app/fichier.py
> ```

## 6. Les manifests

Quatre fichiers, déjà écrits. Le déploiement de l'application reprend volontairement la
section 6.9 du guide de déploiement, celle recommandée pour GKE : `TLS_ENABLED=false`, un
port unique en HTTP simple, le TLS terminé en amont. Tester le banc, c'est donc aussi tester
la documentation.

| Fichier | Contenu |
|---|---|
| [`10-base.yaml`](../bench/k8s-sso/10-base.yaml) | namespace, secrets, PostgreSQL |
| [`20-app.yaml`](../bench/k8s-sso/20-app.yaml) | l'application |
| [`30-keycloak.yaml`](../bench/k8s-sso/30-keycloak.yaml) | le fournisseur d'identité |
| [`40-gateway.yaml`](../bench/k8s-sso/40-gateway.yaml) | la passerelle Envoy |

Deux ajouts spécifiques au banc, tous deux commentés dans `20-app.yaml` : `hostAliases`, qui
fait résoudre les noms publics vers la passerelle depuis l'intérieur du pod (ce que fait un
DNS à horizon partagé en production), et un enrobage de la commande qui ajoute l'autorité
interne au magasin de confiance, parce que la découverte OIDC est faite par l'application
elle-même en TLS.

## 7. Le royaume Keycloak

La configuration de l'IdP est déclarative et importée au démarrage
([`realm-tribe.json`](../bench/k8s-sso/realm-tribe.json)) : un royaume, un client OIDC
confidentiel, un client SAML 2.0, deux utilisateurs, un groupe. Les deux protocoles
travaillent ainsi sur le même annuaire et les mêmes personnes.

Deux réglages non évidents. `saml.client.signature: "false"` dispense l'application de signer
ses AuthnRequests, faute de paire de clés SP. Le mapper de groupes utilise
`full.path: "false"` pour que la revendication vaille `tribe-leads` et non `/tribe-leads`,
sans quoi le mapping vers un rôle applicatif ne correspond jamais.

## 8. Créer les secrets et déployer

```bash
kubectl apply -f 10-base.yaml

kubectl -n tfu create secret generic internal-ca \
  --from-file=ca.crt=pki/ca.crt --dry-run=client -o yaml | kubectl apply -f -

kubectl -n tfu create secret tls gateway-tls \
  --cert=pki/tls.crt --key=pki/tls.key --dry-run=client -o yaml | kubectl apply -f -

kubectl -n tfu create configmap keycloak-realm \
  --from-file=realm-tribe.json --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f 40-gateway.yaml -f 30-keycloak.yaml -f 20-app.yaml

kubectl -n tfu get pods -w      # attendre les 4 pods en Running / 1/1
```

Au démarrage, le pod applicatif attend la base, applique les migrations Alembic, crée le
compte de secours, puis lie un port unique en HTTP simple :

```
kubectl -n tfu logs deploy/teamfollowup-app | tail -20

[entrypoint] Application des migrations Alembic...
[entrypoint] Bootstrap (compte de secours)...
TLS disabled: serving plain HTTP on :8000 (TLS terminated upstream by the infrastructure).
Uvicorn running on http://0.0.0.0:8000
```

## 9. Ouvrir l'accès depuis votre poste

La passerelle est un service interne au cluster. Un port-forward sur le port 443 permet aux
URL publiques de ne pas porter de numéro de port, comme en production.

```bash
kubectl -n tfu port-forward svc/gateway 443:443 --address 127.0.0.1
```

Laissez cette commande tourner dans un terminal dédié. Sous Windows, le port 443 doit être
libre ; vérifiez avec `Get-NetTCPConnection -LocalPort 443 -State Listen`.

> **Piège rencontré.** Le port-forward meurt quand le pod passerelle est remplacé. Après tout
> `rollout restart`, arrêtez le processus `kubectl` résiduel et relancez la commande, sinon le
> port reste occupé et la relance échoue.

## 10. Vérifier la chaîne TLS

Premier contrôle, avec vérification réelle du certificat contre votre autorité.

```bash
curl --cacert pki/ca.crt https://app.localtest.me/api/health
curl --cacert pki/ca.crt https://idp.localtest.me/realms/tribe/.well-known/openid-configuration
```

> **Piège rencontré, sous Windows.** Le `curl` livré avec Git Bash est compilé avec
> **Schannel**, le moteur TLS de Windows : il ignore `--cacert` et échoue en erreur 60.
> Utilisez le pilote Python de l'étape suivante, dont le TLS repose sur OpenSSL et vérifie
> réellement l'autorité.

## 11. Lancer les tests de bout en bout

[`run-tests.py`](../bench/k8s-sso/run-tests.py) joue les deux flux comme un navigateur : il
suit les redirections, remplit le formulaire de connexion Keycloak, revient sur l'application
et vérifie qui est connecté. La vérification du certificat n'est jamais désactivée, et la
résolution DNS est détournée dans le processus plutôt que dans votre fichier `hosts`.

```bash
python run-tests.py
```

```
=== 1. Transport: internal CA, verified ===
  [OK ] app reachable through the gateway over verified TLS
  [OK ] Keycloak reachable on the same certificate

=== 2. Deployment: derived SSO URLs ===
  [OK ] public base URL taken from PUBLIC_BASE_URL   -> https://app.localtest.me
  [OK ] OIDC redirect URI derived
  [OK ] SAML entity ID derived
  [OK ] SAML ACS URL derived

=== 3. OIDC login, end to end ===
  [OK ] app redirects the user to Keycloak
  [OK ] Keycloak accepts the credentials
  [OK ] Keycloak calls back the DERIVED redirect URI
  [OK ] OIDC session established            -> alice@exemple.com / active
  [OK ] IdP group mapped to an application role -> tribe_leader

=== 4. SAML 2.0 login, end to end ===
  [OK ] SP metadata published with the derived URLs
  [OK ] app issues a SAML AuthnRequest to Keycloak
  [OK ] Keycloak authenticates the SAML user
  [OK ] Keycloak posts the assertion to the ACS URL
  [OK ] app accepts the signed assertion (strict mode)
  [OK ] SAML session established            -> alice@exemple.com / active
  [OK ] same identity as the OIDC flow

18/18 verifications passed
```

**Contrôle négatif.** Pour vérifier que le banc n'est pas complaisant, forcez une mauvaise URL
publique et relancez : l'IdP reçoit alors la mauvaise URL de rappel et le flux casse. Un banc
qui reste vert dans ce cas ne prouve rien.

```
PUT /api/admin/auth-config  {"public_base_url": "https://mauvais-hote.example"}
  -> le login s'arrête sur 302, 2 redirections au lieu de 3
```

## 12. Peupler un historique d'accès réel

Facultatif, mais c'est ce qui rend l'écran « Accès » parlant : deux personnes arrivent
réellement par le SSO, l'une en OIDC et l'autre en SAML, atterrissent dans la file d'attente,
puis sont validées ou refusées ([`seed-history.py`](../bench/k8s-sso/seed-history.py)).

```bash
python seed-history.py
```

```
  Alice se connecte via OIDC...
  Bob se connecte via SAML...
  file d'attente : ['alice@exemple.com', 'bob@exemple.com']
  validation d'Alice : HTTP 200
  refus de Bob       : HTTP 200

  access.deny            bob@exemple.com   par Administrateur (compte de secours)
  access.approve         alice@exemple.com (tribe_leader) par Administrateur
  user.provisioned.saml  bob@exemple.com
  user.provisioned.oidc  alice@exemple.com
```

## 13. Parcourir l'application

Ouvrez **https://app.localtest.me**. Votre navigateur affichera un avertissement de
certificat : l'autorité est privée et n'est pas dans son magasin. C'est le comportement
attendu. Passez outre, ou importez `pki/ca.crt` dans les autorités de confiance pour ne plus
l'avoir.

| Quoi | Où | Identifiants |
|---|---|---|
| Application | `https://app.localtest.me` | `admin@local` / `bench-admin-pw` |
| Connexion SSO | les deux boutons de l'écran d'accueil | `alice` / `alice-pw` |
| Keycloak | `https://idp.localtest.me` | `admin` / `admin-pw` |

Le parcours qui montre l'essentiel : connectez-vous en compte de secours, puis
**Administration > Authentification**. La carte « URL publique de l'application » affiche
l'adresse retenue, et en dessous les trois URL de rappel dérivées, prêtes à copier chez l'IdP.
Chaque protocole a son bouton **Tester la connexion à l'IdP**, qui détaille la vérification
étape par étape. Enfin, **Accès** montre la file d'attente et, en dessous, ce qui a déjà été
traité, avec l'auteur de chaque décision.

## 14. Arrêter et nettoyer

```bash
# arrêter le port-forward (Ctrl+C), puis :
minikube delete -p tfu          # supprime le cluster et ses images
rm -rf pki                      # supprime l'autorité et les clés privées
```

Pour seulement mettre en pause sans tout reconstruire : `minikube stop -p tfu`, puis
`minikube start -p tfu` plus tard.

## Les pièges, rassemblés

Ceux qui ont réellement coûté du temps pendant la mise au point, dans l'ordre où on les
rencontre.

| Symptôme | Cause | Remède |
|---|---|---|
| `CA cert does not include key usage extension` | autorité générée sans extensions X.509 | créer l'AC via un fichier de configuration (`make-pki.sh`) |
| curl échoue en erreur 60 malgré `--cacert` | curl Windows compilé avec Schannel, qui ignore l'option | piloter les tests en Python (OpenSSL) |
| un correctif semble sans effet | `minikube image load` n'écrase pas un tag existant | nouveau tag à chaque build, et vérifier dans le pod |
| toutes les redirections manquées par un script | en-tête lu en `Location` alors qu'uvicorn et Envoy l'émettent en minuscules | normaliser les noms d'en-têtes en minuscules |
| Keycloak affiche une erreur au lieu du formulaire | l'URL de rappel envoyée n'est pas déclarée sur le client | vérifier l'URL publique, puis le bouton de test (étape 13) |
| l'IdP de test ne répond plus | serveur HTTP mono-connexion bloqué par un keep-alive | utiliser un serveur multithread |
| connexion impossible en HTTP simple | `COOKIE_SECURE=true` sur une origine non HTTPS | le passer à `false` en local, `true` dès que le TLS est en place |

## Ce que ce banc ne couvre pas

Le cluster est un vrai Kubernetes, mais ce n'est pas GKE Autopilot. Restent à vérifier sur
votre plateforme, indépendamment de l'application : la réconciliation des ressources Gateway
API par le contrôleur `gke-l7-rilb` et sa `HealthCheckPolicy`, l'approvisionnement du
certificat par votre chaîne de confiance, votre DNS interne, et l'admission Autopilot (quotas,
contraintes de sécurité du cluster).

En revanche tout le comportement applicatif est couvert : dérivation des URL publiques,
terminaison TLS en amont, en-têtes transmis, échange OIDC complet, échange SAML complet,
traduction des groupes de l'IdP en rôles applicatifs.
