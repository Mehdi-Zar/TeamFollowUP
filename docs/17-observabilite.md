# 17 - Observabilité : métriques, tableaux de bord et alertes

Jusqu'ici, la seule chose que l'application disait d'elle-même, c'étaient ses
journaux et son journal d'audit. Ils répondent à « qu'est-ce qui s'est passé »,
jamais à « est-ce que ça se passe plus souvent que d'habitude ». Ce document
installe la moitié manquante.

Comme la [16](16-banc-kubernetes-sso.md), il est écrit pour être suivi sans rien
deviner : les outils s'installent ici, chaque métrique est expliquée, chaque
requête est décortiquée, et chaque alerte dit quoi faire quand elle sonne.

**Durée** : 20 minutes pour voir des courbes, une heure pour comprendre ce qu'on
regarde.

---

## 1. Le problème, et ce qu'on y répond

Un journal vous dit qu'une requête a échoué. Il ne vous dit pas que le taux
d'échec est passé de 0,1 % à 4 % depuis vingt minutes, parce que personne ne lit
un million de lignes. Pour ça il faut **agréger dans le temps**, et c'est
exactement ce que fait un système de métriques : l'application tient des
compteurs en mémoire, un collecteur vient les lire à intervalle régulier, et la
différence entre deux lectures donne un débit.

Quatre questions suffisent à couvrir presque tous les incidents. On les appelle
souvent les **quatre signaux d'or** :

| Signal | La question | Ce qu'on regarde ici |
|---|---|---|
| Trafic | combien de requêtes ? | `teamfollowup_http_requests_total` |
| Erreurs | combien échouent ? | le même compteur, filtré sur `status=~"5.."` |
| Latence | combien de temps ? | `teamfollowup_http_request_duration_seconds` |
| Saturation | qu'est-ce qui est plein ? | le pool de connexions à la base |

L'application expose ces quatre-là, plus deux signaux propres à son métier : le
planificateur hebdomadaire et les tentatives de connexion.

---

## 2. Ce que l'application expose

### 2.1 Voir les métriques en trente secondes

L'application sert un point d'entrée `/metrics`. Si vous avez une instance qui
tourne (`docker compose up -d`) :

```bash
curl -s http://localhost:8000/metrics | head -40
```

Vous obtenez du texte, une ligne par série temporelle. C'est le **format
d'exposition Prometheus** : volontairement lisible, pour qu'on puisse le
diagnostiquer avec `curl` sans outillage.

```
# HELP teamfollowup_http_requests_total HTTP requests handled, by route template, method and status class.
# TYPE teamfollowup_http_requests_total counter
teamfollowup_http_requests_total{method="GET",route="/api/dashboard",status="200"} 128.0
teamfollowup_http_requests_total{method="GET",route="/api/squads/{squad_id}",status="200"} 47.0
```

Trois choses à savoir pour lire ça :

- **`# HELP` et `# TYPE`** décrivent la métrique. Ils sont répétés à chaque
  collecte, c'est normal.
- **Ce qui est entre accolades, ce sont les étiquettes** (labels). Chaque
  combinaison d'étiquettes est une **série temporelle** distincte, stockée
  séparément. C'est puissant et c'est le piège principal : voir §2.3.
- **Un `counter` ne fait que monter.** La valeur absolue (`128`) ne veut rien
  dire ; ce qui compte, c'est sa dérivée, que l'on calcule avec `rate()`.

### 2.2 Le catalogue

| Métrique | Type | Étiquettes | Ce qu'elle mesure |
|---|---|---|---|
| `teamfollowup_http_requests_total` | counter | `method`, `route`, `status` | requêtes traitées. La base du trafic et du taux d'erreur. |
| `teamfollowup_http_request_duration_seconds` | histogram | `method`, `route` | temps de traitement. Un histogramme produit trois familles de séries : `_bucket` (combien sous tel seuil), `_sum` et `_count`. |
| `teamfollowup_http_requests_in_flight` | gauge | | requêtes en cours à l'instant T. Monte quand l'application n'arrive plus à suivre. |
| `teamfollowup_logins_total` | counter | `outcome` = `success`, `failure`, `throttled` | connexions par mot de passe local. `throttled` = l'anti-force-brute a refusé avant même de vérifier. |
| `teamfollowup_scheduler_runs_total` | counter | `outcome` = `ok`, `skipped_not_leader`, `error` | tours du planificateur hebdomadaire. `skipped_not_leader` = une autre instance tenait le verrou, ce qui est normal en multi-réplique. |
| `teamfollowup_scheduler_last_success_timestamp_seconds` | gauge | | date du dernier tour réussi. Vaut 0 tant qu'il n'y en a pas eu depuis le démarrage. |
| `teamfollowup_db_pool_capacity` | gauge | | taille configurée du pool de connexions. |
| `teamfollowup_db_pool_in_use` | gauge | | connexions actuellement sorties du pool. |
| `teamfollowup_db_pool_available` | gauge | | connexions inactives, prêtes à servir. |
| `teamfollowup_db_pool_overflow` | gauge | | connexions ouvertes **au-delà** de la taille configurée. Positif = le pool a débordé. Négatif = il reste cette marge. |
| `teamfollowup_build_info` | gauge | `version`, `app_name` | vaut toujours 1. Un déploiement se voit comme un **changement de série**, pas comme un changement de valeur. |

S'y ajoutent les métriques que la bibliothèque Prometheus fournit
gratuitement sur le processus Python : `process_resident_memory_bytes`,
`process_cpu_seconds_total`, `python_gc_objects_collected_total`, etc. Sous
Windows, les `process_*` sont absentes, c'est une limite de la bibliothèque.

### 2.3 La règle qu'il ne faut jamais enfreindre : la cardinalité

L'étiquette `route` porte le **gabarit** de la route, jamais le chemin réel :

```
route="/api/squads/{squad_id}"        et non   route="/api/squads/128"
```

C'est vital. Avec le chemin réel, chaque identifiant de squad, chaque année,
chaque nom de fichier exporté créerait sa propre série temporelle. Une base
Prometheus ne meurt presque jamais du volume de points ; elle meurt du **nombre
de séries**. Un compteur mal étiqueté est le moyen le plus simple de faire tomber
la supervision, et l'incident arrive des semaines plus tard, sans rapport visible
avec le commit fautif.

Le test `backend/tests/test_metrics.py::test_requests_are_counted_by_route_template_not_by_path`
existe pour garder cette propriété. Un second test vérifie qu'un balayage de
chemins inexistants ne peut pas non plus fabriquer des séries à volonté.

**Si vous ajoutez une métrique**, posez-vous une seule question : combien de
valeurs différentes cette étiquette peut-elle prendre ? Si la réponse contient
« autant que d'utilisateurs » ou « autant de lignes en base », l'étiquette est
interdite.

---

## 3. Monter la pile locale

### 3.1 Prérequis

Uniquement **Docker**. Si vous ne l'avez pas, l'installation est décrite au
[§2.1 de la doc 16](16-banc-kubernetes-sso.md) : `winget install -e --id
Docker.DockerDesktop` sous Windows, `brew install --cask docker` sous macOS,
`curl -fsSL https://get.docker.com | sudo sh` sous Linux.

Il faut aussi que l'application tourne. Depuis la racine du dépôt :

```bash
docker compose up -d
curl -s http://localhost:8000/api/health
```

### 3.2 Lancer Prometheus et Grafana

Tout est fourni dans [`ops/`](../ops). Depuis la racine du dépôt :

```bash
docker compose -f ops/docker-compose.observability.yml up -d
```

Cette pile est **séparée** de celle de l'application, volontairement : la
supervision n'est pas le produit, et personne ne doit avoir à lancer Prometheus
pour lancer TeamFollowUP.

Deux conteneurs démarrent :

| Service | Adresse | Rôle |
|---|---|---|
| Prometheus | http://localhost:9090 | collecte les métriques toutes les 15 s, les stocke, évalue les règles d'alerte |
| Grafana | http://localhost:3000 (`admin` / `admin`) | les affiche |

### 3.3 Vérifier que la collecte marche

Ouvrez **http://localhost:9090/targets**. Vous devez voir la cible
`teamfollowup` en **UP**, avec la date de la dernière collecte.

Si elle est en **DOWN**, le message d'erreur dit lequel des trois cas c'est :

| Message | Cause | Remède |
|---|---|---|
| `connection refused` | l'application n'écoute pas sur le port visé | vérifiez `docker compose ps` et le port dans `ops/prometheus/prometheus.yml` |
| `no such host` | `host.docker.internal` n'est pas résolu | sous Linux, c'est le `extra_hosts: host-gateway` du fichier compose qui le fournit ; vérifiez qu'il est bien là |
| `server returned HTTP status 401` | l'application exige un jeton | voir §7 |

`host.docker.internal` est le nom qui, depuis l'intérieur d'un conteneur, désigne
la machine hôte. C'est nécessaire parce que Prometheus et l'application tournent
dans deux piles compose différentes, donc sur deux réseaux différents. Si vous
les mettez dans la même pile, remplacez la cible par `app:8000`.

### 3.4 Première requête

Toujours dans Prometheus, onglet **Graph**, tapez :

```promql
teamfollowup_http_requests_total
```

Vous voyez une ligne par combinaison route/méthode/statut. Cliquez dans
l'application pour générer du trafic, attendez quinze secondes, et les courbes
montent.

---

## 4. Les requêtes à connaître

Prometheus a son propre langage, PromQL. Voici les six requêtes qui couvrent
l'essentiel, chacune décortiquée. Copiez-les dans l'onglet Graph pour les voir.

### Trafic : requêtes par seconde

```promql
sum(rate(teamfollowup_http_requests_total[5m]))
```

- `rate(...[5m])` : la pente du compteur, moyennée sur cinq minutes, en unités
  par seconde. C'est `rate` qui transforme un compteur qui ne fait que monter en
  quelque chose d'interprétable. Il gère aussi les redémarrages : quand le
  compteur repart de zéro, `rate` ne produit pas un pic négatif.
- `sum(...)` : additionne toutes les séries. Sans lui, vous auriez une courbe par
  route, ce qui est justement l'intérêt de la variante suivante.

Les cinq routes les plus appelées :

```promql
topk(5, sum by (route) (rate(teamfollowup_http_requests_total[5m])))
```

- `sum by (route)` : agrège en gardant la route, donc en fusionnant les méthodes
  et les statuts.
- `topk(5, ...)` : ne garde que les cinq plus hautes.

### Erreurs : le taux, pas le compte

```promql
sum(rate(teamfollowup_http_requests_total{status=~"5.."}[5m]))
  /
sum(rate(teamfollowup_http_requests_total[5m]))
```

- `{status=~"5.."}` : `=~` est une correspondance par expression régulière, `5..`
  signifie « 5 suivi de deux caractères », donc toute la famille des 5xx.
- La division donne une **proportion** entre 0 et 1. C'est ce qu'il faut
  surveiller : vingt erreurs par minute, c'est une catastrophe sur une instance
  calme et un bruit de fond sur une instance chargée.

Pour distinguer un problème serveur d'un problème client, remplacez `5..` par
`4..` : un pic de 401 signale plutôt des sessions qui expirent, un pic de 403 un
problème de droits.

### Latence : le 95e centile

```promql
histogram_quantile(0.95,
  sum by (le) (rate(teamfollowup_http_request_duration_seconds_bucket[5m]))
)
```

- Un histogramme compte, pour chaque seuil `le` (*less or equal*), combien de
  requêtes sont passées en dessous. `histogram_quantile` reconstitue un centile à
  partir de ces paliers.
- **`sum by (le)` est obligatoire.** L'étiquette `le` est la seule qui doit
  survivre à l'agrégation ; c'est elle qui porte les seuils. C'est l'erreur la
  plus fréquente en PromQL.
- Pourquoi le 95e centile et pas la moyenne : une moyenne noie les cas lents. Si
  une requête sur vingt met huit secondes, la moyenne reste jolie et
  l'utilisateur, lui, voit huit secondes.

Les exports PPTX et HTML prennent légitimement plusieurs secondes. Pour une vue
qui reflète l'expérience de navigation, excluez-les :

```promql
histogram_quantile(0.95,
  sum by (le) (rate(teamfollowup_http_request_duration_seconds_bucket{route!~".*(pptx|html)"}[5m]))
)
```

Et pour trouver **quelle** route est lente :

```promql
topk(5, histogram_quantile(0.95,
  sum by (le, route) (rate(teamfollowup_http_request_duration_seconds_bucket[5m]))
))
```

### Saturation : la base de données

```promql
teamfollowup_db_pool_in_use
teamfollowup_db_pool_overflow
```

La seconde est la plus parlante. Tant qu'elle est négative, le pool a de la
marge. Dès qu'elle devient positive, le pool est épuisé et l'application ouvre
des connexions supplémentaires : toutes les requêtes attendent, tout devient lent,
et le symptôme ne dit pas d'où ça vient. Cette métrique le dit.

### Connexions : distinguer une attaque d'une panne

```promql
sum by (outcome) (rate(teamfollowup_logins_total[5m]))
```

Trois courbes. Beaucoup de `failure` sans `throttled` évoque une attaque
distribuée (chaque IP reste sous le seuil). Beaucoup de `throttled` évoque plutôt
une intégration cassée qui rejoue les mêmes identifiants périmés en boucle.

### Déploiements : voir la version qui tourne

```promql
teamfollowup_build_info
```

La valeur vaut toujours 1 ; c'est l'étiquette `version` qui change. Superposée aux
courbes d'erreur, elle répond instantanément à « est-ce que ça a commencé avec la
mise en production ? ».

---

## 5. Construire le tableau de bord

Dans Grafana (http://localhost:3000, `admin` / `admin`), la source de données
Prometheus est déjà déclarée : le fichier
`ops/grafana/provisioning/datasources/prometheus.yml` est lu au démarrage, vous
n'avez pas d'assistant à traverser.

Créez un tableau de bord, ajoutez un panneau, choisissez la source **Prometheus**
et collez une des requêtes ci-dessus dans le champ **Metrics browser**. Les six
panneaux qui valent la peine :

| Panneau | Requête | Type | Réglage utile |
|---|---|---|---|
| Trafic | `sum(rate(teamfollowup_http_requests_total[5m]))` | Time series | unité : requêtes/s |
| Taux d'erreur | la division du §4 | Time series | unité : `Percent (0.0-1.0)` |
| Latence p95 | `histogram_quantile(...)` sans les exports | Time series | unité : `seconds (s)` |
| Top routes lentes | la variante `topk` par route | Table | |
| Pool de connexions | `teamfollowup_db_pool_in_use` et `teamfollowup_db_pool_overflow` | Time series | deux requêtes dans le même panneau |
| Version déployée | `teamfollowup_build_info` | Stat | champ affiché : `version` |

**Aucun fichier de tableau de bord n'est livré dans le dépôt**, et c'est
volontaire : un JSON Grafana non testé qui refuse de s'importer est pire
qu'inutile, et je n'ai pas pu faire tourner Grafana pour le vérifier. Les
requêtes ci-dessus, elles, sont exactes et se collent en quelques minutes. Une
fois votre tableau de bord monté, exportez-le (Share, Export, Save to file) et
posez-le dans `ops/grafana/` pour l'équipe.

---

## 6. Les alertes, et quoi faire quand elles sonnent

Les sept règles sont dans [`ops/prometheus/alerts.yml`](../ops/prometheus/alerts.yml),
chargées automatiquement par la pile locale. Vous les voyez dans Prometheus,
onglet **Alerts**.

Deux notions avant de les lire :

- **`for:`** est le délai pendant lequel la condition doit rester vraie avant que
  l'alerte ne passe de *pending* à *firing*. C'est ce qui évite qu'un unique
  point de mesure malheureux réveille quelqu'un. Une alerte qui crie pour rien
  apprend à tout le monde à l'ignorer, ce qui est pire que pas d'alerte du tout.
- **`severity`** est une simple étiquette : c'est votre Alertmanager qui décide
  quoi en faire (courriel, Slack, astreinte). Cette pile locale n'inclut pas
  d'Alertmanager, les alertes s'affichent seulement dans l'interface.

| Alerte | Se déclenche quand | Premier réflexe |
|---|---|---|
| **TeamFollowUPDown** | la collecte échoue depuis 2 min | `kubectl get pods` ou `docker compose ps`, puis les journaux. Le processus est mort, ou trop occupé pour répondre. |
| **TeamFollowUPHighErrorRate** | plus de 5 % de 5xx sur 5 min | ventilez par route : `topk(5, sum by (route) (rate(teamfollowup_http_requests_total{status=~"5.."}[5m])))`, puis les journaux de cette route |
| **TeamFollowUPSlowRequests** | p95 au-dessus de 2 s sur 10 min, exports exclus | regardez d'abord le pool de connexions, ensuite si un export tourne sur un périmètre énorme, ensuite la charge du nœud |
| **TeamFollowUPExportsVerySlow** | p95 des exports au-dessus de 30 s sur 15 min | la taille du périmètre exporté, et la charge de la base |
| **TeamFollowUPDatabasePoolExhausted** | `overflow > 0` pendant 5 min | soit une requête garde des connexions trop longtemps, soit le pool est sous-dimensionné pour la charge |
| **TeamFollowUPSchedulerStale** | aucun tour réussi depuis 2 h | cherchez `weekly scheduler error` dans les journaux, et vérifiez que le verrou consultatif Postgres n'est pas tenu par une réplique morte |
| **TeamFollowUPLoginFailureSpike** | plus d'un échec par seconde sur 10 min | recoupez avec le journal d'audit et la courbe `throttled` (voir §4) |

Pour brancher de vraies notifications, ajoutez un
[Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) à la pile
et déclarez-le dans `ops/prometheus/prometheus.yml` sous `alerting:`. C'est lui
qui groupe, met en sourdine et route vers les canaux.

---

## 7. Protéger `/metrics`

Le point d'entrée décrit votre trafic : quelles routes existent, à quelle
fréquence elles sont appelées, combien d'erreurs. Ce n'est pas un secret, mais ce
n'est pas non plus à donner à Internet.

L'application binde **un seul port**, celui par lequel arrivent aussi les
utilisateurs. Donc, sans action de votre part, `/metrics` est joignable par qui
peut joindre l'application. Deux protections, et il en faut **au moins une** :

### Option A, la plus propre : ne pas router `/metrics` publiquement

Sur une passerelle GKE, ne déclarez pas ce chemin dans l'`HTTPRoute` public, ou
ajoutez une règle qui le refuse. Le scraper, lui, tourne dans le cluster et
s'adresse directement au pod, sans passer par la passerelle. Il n'a donc pas
besoin que le chemin soit exposé.

### Option B : exiger un jeton

```bash
# une valeur aléatoire, gardée dans votre coffre à secrets
METRICS_TOKEN=$(openssl rand -hex 32)
```

Posez-la sur l'application (variable `METRICS_TOKEN`), puis donnez la même au
scraper. Dans `ops/prometheus/prometheus.yml`, décommentez :

```yaml
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/metrics-token
```

et écrivez le jeton, seul, dans `ops/prometheus/metrics-token`. Prometheus lit ce
fichier au moment de la collecte : le jeton n'apparaît ni dans la ligne de
commande, ni dans la configuration.

Sans jeton présenté, l'application répond **401** avec un en-tête
`WWW-Authenticate: Bearer`, pour qu'un scraper mal configuré signale
« non autorisé » au lieu d'échouer sur une page d'erreur illisible.

### Le garde-fou au démarrage

Si `PUBLIC_BASE_URL` est renseignée (donc : ce n'est pas un poste de
développement) et que `METRICS_TOKEN` est vide, l'application écrit un
avertissement dans ses journaux au démarrage :

```
SECURITY: /metrics is enabled without METRICS_TOKEN while PUBLIC_BASE_URL is set -
keep /metrics off the public route, or set METRICS_TOKEN (docs/17).
```

C'est le même mécanisme que pour la clé de signature ou le mot de passe de base
laissés à leur valeur par défaut.

### Tout couper

`METRICS_ENABLED=false` désactive l'intercepteur **et** le point d'entrée, qui
répond alors 404. Aucune mesure n'est prise, aucun coût n'est payé.

---

## 8. Sur Kubernetes

### 8.1 Avec l'opérateur Prometheus (le cas courant)

Déclarez un `ServiceMonitor` qui cible le Service de l'application :

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: teamfollowup
  namespace: tfu
spec:
  selector:
    matchLabels:
      app: teamfollowup-app        # les labels du Service, pas du Deployment
  endpoints:
    - port: http                   # le NOM du port dans le Service, pas son numéro
      path: /metrics
      interval: 30s
```

Les deux erreurs classiques sont dans les commentaires : le sélecteur porte sur le
**Service**, et `port` attend le **nom** du port, ce qui suppose que votre Service
nomme ses ports (celui de `bench/k8s-sso/20-app.yaml` le fait : `name: http`).

### 8.2 Sur GKE, avec Google Managed Prometheus

GKE propose une collecte managée : pas de Prometheus à exploiter, les métriques
arrivent dans Cloud Monitoring et se requêtent en PromQL comme ailleurs.

```yaml
apiVersion: monitoring.googleapis.com/v1
kind: PodMonitoring
metadata:
  name: teamfollowup
  namespace: tfu
spec:
  selector:
    matchLabels:
      app: teamfollowup-app
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

`PodMonitoring` cible les **pods** directement, donc le scraper ne passe pas par
la passerelle : l'option A du §7 (ne pas router `/metrics` publiquement) reste
valable et suffisante.

Les règles d'alerte de `ops/prometheus/alerts.yml` se reprennent telles quelles
dans une ressource `Rules` (Managed Prometheus) ou `PrometheusRule` (opérateur) :
le bloc `groups:` a le même schéma dans les trois cas.

---

## 9. Ce que ce dispositif ne couvre pas

- **Les traces distribuées.** Avec une seule application et une base, une trace
  n'apporterait pas grand-chose que le p95 par route ne dise déjà. Le jour où des
  appels sortants s'ajoutent, OpenTelemetry devient le bon outil.
- **Les journaux.** Ils sont déjà traités ailleurs : `LOG_FORMAT=json` produit des
  entrées structurées que Cloud Logging analyse nativement, l'écran
  Administration > Ops montre le tampon récent, et Administration > Logs exporte
  le journal d'audit vers syslog, GCS ou BigQuery.
- **La sonde externe.** Toutes les métriques d'ici sont produites **par**
  l'application : si elle est morte, elles ne disent rien, et c'est l'absence de
  collecte qui fait sonner `TeamFollowUPDown`. Une sonde depuis l'extérieur
  (Uptime Kuma, Cloud Monitoring uptime check) reste utile pour vérifier le
  chemin complet, DNS et certificat compris.
- **Les métriques métier** (nombre de squads, d'objectifs en retard). Elles
  demanderaient une requête en base **à chaque collecte**, donc toutes les quinze
  secondes, pour toujours : un plancher de charge permanent pour une information
  qui n'a pas besoin d'être à la seconde. Le tableau de bord de l'application la
  donne déjà, à la demande.

---

## 10. Récapitulatif des variables

| Variable | Défaut | Effet |
|---|---|---|
| `METRICS_ENABLED` | `true` | `false` désactive l'intercepteur et fait répondre 404 à `/metrics` |
| `METRICS_TOKEN` | vide | vide = point d'entrée ouvert ; renseignée = jeton `Bearer` exigé |

Elles sont documentées dans les deux `.env.example` et dans le tableau des
variables du [guide de déploiement](12-deployment-guide.md).
