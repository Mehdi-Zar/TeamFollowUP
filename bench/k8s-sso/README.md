# Banc Kubernetes, OIDC et SAML

Ce dossier contient tout ce qui est rejouable du banc de test de bout en bout :
TeamFollowUP dans un vrai cluster, derrière une passerelle qui termine le TLS avec
une autorité interne, avec Keycloak en fournisseur d'identité parlant **OIDC et
SAML 2.0** sur le même royaume et le même utilisateur.

Le mode d'emploi complet, étape par étape, est dans
[`docs/16-banc-kubernetes-sso.md`](../../docs/16-banc-kubernetes-sso.md).

| Fichier | Rôle |
|---|---|
| `make-pki.sh` | génère l'autorité interne et le certificat serveur dans `pki/` (jamais versionné) |
| `10-base.yaml` | namespace, secrets du banc, PostgreSQL |
| `20-app.yaml` | l'application, déployée comme la section 6.9 du guide de déploiement le prescrit (`TLS_ENABLED=false`, port unique en HTTP) |
| `30-keycloak.yaml` | le fournisseur d'identité, royaume importé au démarrage |
| `40-gateway.yaml` | la passerelle Envoy : terminaison TLS, en-têtes transmis comme le fait un ALB Google |
| `realm-tribe.json` | le royaume Keycloak : client OIDC, client SAML, mappers, utilisateurs, groupe |
| `run-tests.py` | le pilote : 18 vérifications, connexion OIDC complète puis connexion SAML complète |
| `seed-history.py` | facultatif : deux arrivées réelles par SSO, une validation et un refus, pour peupler l'écran Accès |

Démarrage rapide, depuis ce dossier :

```bash
./make-pki.sh
minikube start --driver=docker --cpus=4 --memory=6144 --profile=tfu
docker build -t teamfollowup-app:bench ../..
# suite (chargement des images, secrets, déploiement, tests) : docs/16
python run-tests.py
```

Les mots de passe présents dans `10-base.yaml`, `30-keycloak.yaml` et `realm-tribe.json`
sont **jetables** et n'existent que dans ce cluster local. Ils ne servent nulle part
ailleurs et ne doivent jamais être réutilisés.
