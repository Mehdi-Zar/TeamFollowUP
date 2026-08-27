# Banc Kubernetes, OIDC et SAML

Ce dossier contient tout ce qui est rejouable du banc de test de bout en bout :
TeamFollowUP dans un vrai cluster, derrière une passerelle qui termine le TLS avec
une autorité interne, avec Keycloak en fournisseur d'identité parlant **OIDC et
SAML 2.0** sur le même royaume et le même utilisateur.

**Le mode d'emploi est [`docs/16-banc-kubernetes-sso.md`](../../docs/16-banc-kubernetes-sso.md).**
Il part de l'installation des outils, explique chaque commande et chaque fichier de
ce dossier, et dit à chaque étape ce que vous devez voir pour savoir qu'elle a
marché. Ne suivez pas le résumé ci-dessous sans l'avoir lu au moins une fois : il
omet les prérequis, les pièges et les vérifications.

| Fichier | Rôle |
|---|---|
| `make-pki.sh` | génère l'autorité interne et le certificat serveur dans `pki/` (jamais versionné) |
| `10-base.yaml` | namespace, secrets du banc, PostgreSQL |
| `20-app.yaml` | l'application, déployée comme la section 6.9 du guide de déploiement le prescrit (`TLS_ENABLED=false`, port unique en HTTP) |
| `30-keycloak.yaml` | le fournisseur d'identité, royaume importé au démarrage |
| `40-gateway.yaml` | la passerelle Envoy : terminaison TLS, en-têtes transmis comme le fait un ALB Google |
| `realm-tribe.json` | le royaume Keycloak : client OIDC, client SAML, mappers, utilisateurs, groupe |
| `run-tests.py` | le pilote : 18 vérifications, connexion OIDC complète puis connexion SAML complète. Il configure lui-même le SSO par l'API d'administration, puis remet tout à zéro. |
| `seed-history.py` | facultatif : deux arrivées réelles par SSO, une validation et un refus, pour peupler l'écran Accès |

Résumé des commandes, depuis ce dossier, une fois les outils installés :

```bash
./make-pki.sh                                              # autorité + certificat
minikube start --driver=docker --cpus=4 --memory=6144 --profile=tfu
kubectl config use-context tfu
docker build -t teamfollowup-app:bench-v6 ../..            # tag = celui de 20-app.yaml
for i in teamfollowup-app:bench-v6 postgres:16-alpine \
         envoyproxy/envoy:v1.31-latest quay.io/keycloak/keycloak:26.0; do
  minikube -p tfu image load "$i"
done
kubectl apply -f 10-base.yaml
kubectl -n tfu create secret generic internal-ca --from-file=ca.crt=pki/ca.crt --dry-run=client -o yaml | kubectl apply -f -
kubectl -n tfu create secret tls gateway-tls --cert=pki/tls.crt --key=pki/tls.key --dry-run=client -o yaml | kubectl apply -f -
kubectl -n tfu create configmap keycloak-realm --from-file=realm-tribe.json --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f 40-gateway.yaml -f 30-keycloak.yaml -f 20-app.yaml
kubectl -n tfu get pods -w                                 # attendre 4 pods Running 1/1
kubectl -n tfu port-forward svc/gateway 443:443 --address 127.0.0.1   # terminal dédié
python run-tests.py                                        # 18/18 attendu
```

Nettoyage : `minikube delete -p tfu` puis `rm -rf pki`.

Les mots de passe présents dans `10-base.yaml`, `30-keycloak.yaml` et `realm-tribe.json`
sont **jetables** et n'existent que dans ce cluster local. Ils ne servent nulle part
ailleurs et ne doivent jamais être réutilisés.
